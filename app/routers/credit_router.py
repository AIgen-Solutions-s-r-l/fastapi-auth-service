"""Router for credit-related endpoints."""

from decimal import Decimal
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_active_user
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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's credit balance.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        CreditBalanceResponse: Current balance and last update time
    """
    credit_service = CreditService(db)
    return await credit_service.get_balance(current_user.id)


@router.post("/use", response_model=TransactionResponse)
async def use_credits(
    request: CreditsUseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Use credits from user's balance.
    
    Args:
        request: Credits use request
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        TransactionResponse: Transaction details
        
    Raises:
        HTTPException: If user has insufficient credits
    """
    try:
        credit_service = CreditService(db)
        return await credit_service.use_credits(
            user_id=current_user.id,
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits to user's balance.
    
    Args:
        request: Credits add request
        background_tasks: FastAPI background tasks
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        TransactionResponse: Transaction details
    """
    credit_service = CreditService(db)
    return await credit_service.add_credits(
        user_id=current_user.id,
        amount=request.amount,
        reference_id=request.reference_id,
        description=request.description
    )


@router.get("/transactions", response_model=TransactionHistoryResponse)
async def get_transaction_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's transaction history.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        TransactionHistoryResponse: List of transactions and total count
    """
    credit_service = CreditService(db)
    return await credit_service.get_transaction_history(
        user_id=current_user.id,
        skip=skip,
        limit=limit
    )


@router.post("/stripe/add", response_model=StripeTransactionResponse)
async def add_credits_from_stripe(
    request: StripeTransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits based on a Stripe transaction.
    
    This endpoint receives a request with either:
    - A transaction ID 
    - An email address
    
    It then:
    1. Looks up the transaction in Stripe
    2. Analyzes the transaction to determine the type (subscription or oneoff)
    3. Adds the appropriate credits to the user's account
    
    Args:
        request: Stripe transaction request
        background_tasks: FastAPI background tasks
        current_user: Current authenticated user
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
        user = await user_service.get_user_by_id(current_user.id)
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
        
        # Validate transaction type matches the requested type
        if analysis["transaction_type"] != request.transaction_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction type mismatch. Requested: {request.transaction_type}, Found: {analysis['transaction_type']}"
            )
        
        # Process based on transaction type
        if analysis["transaction_type"] == "subscription":
            # Handle subscription
            subscription_id = analysis.get("subscription_id")
            if not subscription_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subscription ID not found in transaction data"
                )
            
            # Look up plan ID based on the Stripe plan ID
            plan_id = None
            stripe_plan_id = analysis.get("plan_id")
            
            if stripe_plan_id:
                # Get plans from database to find the matching plan
                plans = await credit_service.get_all_active_plans()
                matching_plans = [p for p in plans if p.stripe_price_id == stripe_plan_id]
                
                if matching_plans:
                    plan_id = matching_plans[0].id
                else:
                    # If no exact match found, fallback to a default plan
                    # In production, you might want to create a new plan or raise an error
                    if plans:
                        plan_id = plans[0].id
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail="No matching plan found for this subscription"
                        )
            else:
                # If no plan ID in analysis, use a default plan
                # Get the first active plan as a fallback
                plans = await credit_service.get_all_active_plans()
                if plans:
                    plan_id = plans[0].id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No active plans found in the system"
                    )
            
            # Purchase plan or handle renewal
            transaction, subscription = await credit_service.purchase_plan(
                user_id=user.id,
                plan_id=plan_id,
                reference_id=analysis["transaction_id"],
                description=f"Subscription from Stripe: {subscription_id}",
                background_tasks=background_tasks
            )
            
            # Update subscription with Stripe IDs
            # This would typically be done in the purchase_plan method in a production environment
            
            logger.info(f"Processed subscription from Stripe",
                      event_type="stripe_subscription_processed",
                      user_id=user.id,
                      stripe_transaction_id=analysis["transaction_id"],
                      stripe_subscription_id=subscription_id,
                      plan_id=plan_id,
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
                    subscription_id=subscription_id,
                    plan_id=analysis.get("plan_id"),
                    product_id=analysis.get("product_id")
                ),
                credit_transaction_id=transaction.id,
                subscription_id=subscription.id,
                new_balance=transaction.new_balance
            )
            
        else:
            # Handle one-time purchase
            # Find appropriate plan or credit calculation based on the payment amount
            plans = await credit_service.get_all_active_plans()
            
            # Calculate credit amount based on similar plans
            # This approaches finds the best credit-to-dollar ratio from existing plans
            # rather than using a hardcoded conversion rate
            credit_amount = None
            
            if plans:
                # Find plans with similar prices
                payment_amount = analysis["amount"]
                similar_plans = sorted(plans, key=lambda p: abs(p.price - payment_amount))
                
                if similar_plans:
                    # Use the most similar plan's credit-to-price ratio to calculate credits
                    best_match = similar_plans[0]
                    ratio = best_match.credit_amount / best_match.price
                    credit_amount = payment_amount * ratio
                    
                    logger.info(f"Calculated credits using plan-based ratio",
                              event_type="credit_calculation",
                              payment_amount=payment_amount,
                              similar_plan_id=best_match.id,
                              ratio=float(ratio),
                              credit_amount=float(credit_amount))
            
            # Fallback if no plans found or calculation resulted in zero credits
            if not credit_amount or credit_amount <= 0:
                # Use a default ratio as fallback (e.g., $1 = 10 credits)
                credit_amount = analysis["amount"] * Decimal('10')
                logger.warning(f"Using fallback credit calculation",
                             event_type="credit_calculation_fallback",
                             payment_amount=float(analysis["amount"]),
                             credit_amount=float(credit_amount))
            
            # Add credits
            transaction = await credit_service.purchase_one_time_credits(
                user_id=user.id,
                amount=credit_amount,
                price=analysis["amount"],
                reference_id=analysis["transaction_id"],
                description=f"One-time purchase from Stripe: {analysis['transaction_id']}",
                background_tasks=background_tasks
            )
            
            logger.info(f"Processed one-time purchase from Stripe",
                      event_type="stripe_oneoff_processed",
                      user_id=user.id,
                      stripe_transaction_id=analysis["transaction_id"],
                      credit_amount=credit_amount,
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
                   user_id=current_user.id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing Stripe transaction: {str(e)}"
        )