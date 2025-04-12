"""Router for credit-related endpoints."""

from decimal import Decimal
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_internal_service, get_current_user
from app.models.user import User
from app.schemas.credit_schemas import (
    TransactionResponse,
    TransactionHistoryResponse,
    CreditBalanceResponse,
    UseCreditRequest as CreditsUseRequest,
    AddCreditRequest as CreditsAddRequest
)
from app.schemas.stripe_schemas import (
    StripeTransactionRequest,
    StripeTransaction,
    StripeTransactionResponse
)
from app.services.credit_service import CreditService, InsufficientCreditsError
from app.services.user_service import UserService
from app.services.stripe_service import StripeService
from app.log.logging import logger


router = APIRouter(prefix="/credits", tags=["credits"])

@router.get("/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    user_id: int,
    _: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's credit balance.
    
    This endpoint is restricted to internal service access only.
    
    Args:
        user_id: ID of the user to get balance for
        _: Internal service identifier (from API key auth)
        db: Database session
        
    Returns:
        CreditBalanceResponse: Current balance and last update time
    """
    credit_service = CreditService(db)
    return await credit_service.get_balance(user_id)



@router.post("/use", response_model=TransactionResponse)
async def use_credits(
    request: CreditsUseRequest,
    user_id: int,
    _: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Use credits from user's balance.
    
    This endpoint is restricted to internal service access only.
    
    Args:
        request: Credits use request
        user_id: ID of the user to use credits for
        _: Internal service identifier (from API key auth)
        db: Database session
        
    Returns:
        TransactionResponse: Transaction details
        
    Raises:
        HTTPException: If user has insufficient credits
    """
    try:
        credit_service = CreditService(db)
        return await credit_service.use_credits(
            user_id=user_id,
            amount=request.amount,
            reference_id=request.reference_id,
            description=request.description
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/add", response_model=TransactionResponse)
async def add_credits(
    request: CreditsAddRequest,
    user_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits to user's balance.
    
    This endpoint is restricted to internal service access only.
    
    Args:
        request: Credits add request
        user_id: ID of the user to add credits for
        background_tasks: FastAPI background tasks
        _: Internal service identifier (from API key auth)
        db: Database session
        
    Returns:
        TransactionResponse: Transaction details
    """
    logger.info(f"Adding credits: User {user_id}, Amount {request.amount}",
              event_type="add_credits_request",
              user_id=user_id,
              amount=request.amount,
              reference_id=request.reference_id)
    
    credit_service = CreditService(db)
    
    try:
        # Check if reference_id is a Stripe transaction ID
        if request.reference_id and request.reference_id.startswith(("pi_", "sub_", "in_", "ch_")):
            logger.info(f"Detected potential Stripe transaction ID: {request.reference_id}",
                      event_type="stripe_transaction_detected",
                      user_id=user_id,
                      reference_id=request.reference_id)
            
            # Determine transaction type based on prefix
            if request.reference_id.startswith("sub_"):
                # Handle as subscription
                logger.info(f"Processing as subscription: {request.reference_id}",
                          event_type="processing_subscription",
                          user_id=user_id,
                          subscription_id=request.reference_id)
                
                transaction, subscription = await credit_service.verify_and_process_subscription(
                    user_id=user_id,
                    transaction_id=request.reference_id,
                    background_tasks=background_tasks
                )
                
                logger.info(f"Subscription processed successfully: {request.reference_id}",
                          event_type="subscription_processed",
                          user_id=user_id,
                          subscription_id=subscription.id,
                          transaction_id=transaction.id,
                          new_balance=transaction.new_balance)
                
                return transaction
                
            else:
                # Handle as one-time payment
                logger.info(f"Processing as one-time payment: {request.reference_id}",
                          event_type="processing_one_time_payment",
                          user_id=user_id,
                          transaction_id=request.reference_id)
                
                transaction = await credit_service.verify_and_process_one_time_payment(
                    user_id=user_id,
                    transaction_id=request.reference_id,
                    background_tasks=background_tasks,
                    amount=request.amount
                )
                
                logger.info(f"One-time payment processed successfully: {request.reference_id}",
                          event_type="one_time_payment_processed",
                          user_id=user_id,
                          transaction_id=transaction.id,
                          new_balance=transaction.new_balance)
                
                return transaction
        
        # If not a Stripe transaction ID, process as regular credit addition
        logger.info(f"Processing as regular credit addition: User {user_id}, Amount {request.amount}",
                  event_type="regular_credit_addition",
                  user_id=user_id,
                  amount=request.amount,
                  reference_id=request.reference_id)
        
        return await credit_service.add_credits(
            user_id=user_id,
            amount=request.amount,
            reference_id=request.reference_id,
            description=request.description
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(f"Error adding credits: {str(e)}",
                   event_type="add_credits_error",
                   user_id=user_id,
                   amount=request.amount,
                   reference_id=request.reference_id,
                   error=str(e))
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding credits: {str(e)}"
        )
@router.get("/transactions", response_model=TransactionHistoryResponse)
async def get_transaction_history(
    user_id: int,
    skip: int = 0,
    limit: int = 50,
    _: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's transaction history.
    
    This endpoint is restricted to internal service access only.
    
    Args:
        user_id: ID of the user to get transaction history for
        skip: Number of records to skip
        limit: Maximum number of records to return
        _: Internal service identifier (from API key auth)
        db: Database session
        
    Returns:
        TransactionHistoryResponse: List of transactions and total count
    """
    credit_service = CreditService(db)
    return await credit_service.get_transaction_history(
        user_id=user_id,
        skip=skip,
        limit=limit
    )

@router.get("/user/transactions", response_model=TransactionHistoryResponse)
async def get_user_transaction_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get transaction history for the authenticated user.
    
    This endpoint is accessible to authenticated users to view their own transaction history.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        current_user: Authenticated user (from JWT token)
        db: Database session
        
    Returns:
        TransactionHistoryResponse: List of transactions and total count
    """
    logger.info(f"User {current_user.id} requesting their transaction history",
               event_type="user_transaction_history_request",
               user_id=current_user.id,
               skip=skip,
               limit=limit)
    
    # Log user details for debugging
    logger.info(f"User details: ID {current_user.id}, Email {current_user.email}",
               event_type="user_transaction_history_user_details",
               user_id=current_user.id,
               user_email=current_user.email)
    
    credit_service = CreditService(db)
    response = await credit_service.get_transaction_history(
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )

    for tx in response.transactions:
        if tx.subscription_id:
            subscription = await credit_service.get_subscription_by_id(tx.subscription_id)
            tx.is_subscription_active = subscription and (subscription.status == "active")
        else:
            tx.is_subscription_active = None
    
    # Log response details for debugging
    logger.info(f"Transaction history response: {len(response.transactions)} transactions, Total count {response.total_count}",
               event_type="user_transaction_history_response",
               user_id=current_user.id,
               returned_count=len(response.transactions),
               total_count=response.total_count,
               transaction_ids=[tx.id for tx in response.transactions])
    
    return response


@router.post("/stripe/add", response_model=StripeTransactionResponse)
async def add_credits_from_stripe(
    request: StripeTransactionRequest,
    user_id: int,
    background_tasks: BackgroundTasks,
    _: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits based on a Stripe transaction.
    
    This endpoint is restricted to internal service access only.
    
    This endpoint receives a request with either:
    - A transaction ID
    - An email address
    
    It then:
    1. Looks up the transaction in Stripe
    2. Analyzes the transaction to determine the type (subscription or oneoff)
    3. Adds the appropriate credits to the user's account
    
    Args:
        request: Stripe transaction request
        user_id: ID of the user to add credits for
        background_tasks: FastAPI background tasks
        _: Internal service identifier (from API key auth)
        db: Database session
        
    Returns:
        StripeTransactionResponse: Processing result
        
    Raises:
        HTTPException: If transaction not found or other error occurs
    """
    try:
        # Initialize services
        user_service = UserService(db)
        credit_service = CreditService(db)
        stripe_service = StripeService()
        
        # Get user
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Log processing
        logger.info(f"Processing Stripe transaction",
                  event_type="stripe_transaction_processing",
                  user_id=user.id,
                  transaction_type=request.transaction_type,
                  has_transaction_id=request.transaction_id is not None,
                  has_email=request.email is not None)
        
        # Find transaction by ID or email
        transaction_data = None
        if request.transaction_id:
            # Find by transaction ID
            transaction_data = await stripe_service.find_transaction_by_id(request.transaction_id)
            if not transaction_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Transaction not found: {request.transaction_id}"
                )
        elif request.email:
            # Find by email
            transactions = await stripe_service.find_transactions_by_email(request.email)
            if not transactions:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No transactions found for email: {request.email}"
                )
            
            # Filter by transaction type if specified
            matching_transactions = []
            for tx in transactions:
                # For subscription type, look for subscription object types
                if request.transaction_type == "subscription" and tx.get("object_type") in ["subscription", "invoice"]:
                    matching_transactions.append(tx)
                # For oneoff type, look for payment_intent or charge object types
                elif request.transaction_type == "oneoff" and tx.get("object_type") in ["payment_intent", "charge"]:
                    matching_transactions.append(tx)
            
            if not matching_transactions:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No {request.transaction_type} transactions found for email: {request.email}"
                )
            
            # Use the most recent matching transaction
            transaction_data = matching_transactions[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either transaction_id or email must be provided"
            )
        
        # Analyze transaction
        analysis = await stripe_service.analyze_transaction(transaction_data)
        
        # Use the amount directly from the request
        logger.info(f"Using amount directly from request: {request.transaction_type}",
                  event_type="direct_amount_processing",
                  user_id=user_id,
                  transaction_type=request.transaction_type)
        
        # Validate transaction type matches the requested type
        if analysis["transaction_type"] != request.transaction_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction type mismatch. Requested: {request.transaction_type}, Found: {analysis['transaction_type']}"
            )
        
        # Process based on transaction type
        if analysis["transaction_type"] == "subscription":
            # Handle subscription
            if not analysis.get("subscription_id"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subscription ID not found in transaction data"
                )
            
            # Process subscription using the new method
            transaction, subscription = await credit_service.verify_and_process_subscription(
                user_id=user.id,
                transaction_id=analysis["subscription_id"],
                background_tasks=background_tasks
            )
            
            logger.info(f"Processed subscription from Stripe",
                      event_type="stripe_subscription_processed",
                      user_id=user.id,
                      stripe_transaction_id=analysis["transaction_id"],
                      stripe_subscription_id=analysis["subscription_id"],
                      plan_id=subscription.plan_id,
                      subscription_id=subscription.id,
                      credit_transaction_id=transaction.id)
            
            # Create response
            return StripeTransactionResponse(
                applied=True,
                transaction=StripeTransaction(
                    transaction_id=analysis["transaction_id"],
                    transaction_type=analysis["transaction_type"],
                    amount=analysis["amount"],
                    customer_id=analysis["customer_id"],
                    customer_email=analysis["customer_email"],
                    created_at=analysis["created_at"],
                    subscription_id=analysis["subscription_id"],
                    plan_id=analysis.get("plan_id"),
                    product_id=analysis.get("product_id")
                ),
                credit_transaction_id=transaction.id,
                subscription_id=subscription.id,
                new_balance=transaction.new_balance
            )
            
        else:
            # Handle one-time purchase using the new method
            # For one-time purchases, we use the amount from the metadata if available
            amount = None
            if request.metadata and "amount" in request.metadata:
                amount = Decimal(str(request.metadata["amount"]))
                logger.info(f"Using amount from metadata: {amount}",
                          event_type="using_metadata_amount",
                          user_id=user.id,
                          amount=float(amount))
            
            transaction = await credit_service.verify_and_process_one_time_payment(
                user_id=user.id,
                transaction_id=analysis["transaction_id"],
                background_tasks=background_tasks,
                amount=amount
            )
            
            logger.info(f"Processed one-time purchase from Stripe",
                      event_type="stripe_oneoff_processed",
                      user_id=user.id,
                      stripe_transaction_id=analysis["transaction_id"],
                      credit_amount=transaction.amount,
                      credit_transaction_id=transaction.id)
            
            # Create response
            return StripeTransactionResponse(
                applied=True,
                transaction=StripeTransaction(
                    transaction_id=analysis["transaction_id"],
                    transaction_type=analysis["transaction_type"],
                    amount=analysis["amount"],
                    customer_id=analysis["customer_id"],
                    customer_email=analysis["customer_email"],
                    created_at=analysis["created_at"],
                    product_id=analysis.get("product_id")
                ),
                credit_transaction_id=transaction.id,
                new_balance=transaction.new_balance
            )
            
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.error(f"Error processing Stripe transaction: {str(e)}",
                   event_type="stripe_processing_error",
                   user_id=user_id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing Stripe transaction: {str(e)}"
        )