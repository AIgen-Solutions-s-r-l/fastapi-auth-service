"""Router for credit-related endpoints."""

from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from app.log.logging import logger 
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.responses import DecimalJSONResponse
from app.models.user import User
from app.schemas import credit_schemas, plan_schemas
from app.services.credit_service import CreditService, InsufficientCreditsError
from app.services.user_service import UserService

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get(
    "/balance",
    response_model=credit_schemas.CreditBalanceResponse,
    response_class=DecimalJSONResponse
)
async def get_credit_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's credit balance.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        CreditBalanceResponse: Current credit balance
    """
    credit_service = CreditService(db)
    user_id = current_user.id if isinstance(current_user, User) else current_user['id']
    return await credit_service.get_balance(user_id)


@router.post(
    "/add",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def add_credits(
    request: credit_schemas.AddCreditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits to user's balance.

    Args:
        request: Credit addition details
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    credit_service = CreditService(db)
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        return await credit_service.add_credits(
            user_id=user_id,
            amount=request.amount,
            reference_id=request.reference_id,
            description=request.description
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error adding credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing credit addition"
        )


@router.post(
    "/use",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def use_credits(
    request: credit_schemas.UseCreditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Use credits from user's balance.

    Args:
        request: Credit usage details
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    credit_service = CreditService(db)
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
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
    except Exception as e:
        logger.exception(f"Error using credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing credit usage"
        )


@router.get(
    "/transactions",
    response_model=credit_schemas.TransactionHistoryResponse,
    response_class=DecimalJSONResponse
)
async def get_transaction_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's credit transaction history.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionHistoryResponse: List of transactions and total count
    """
    credit_service = CreditService(db)
    user_id = current_user.id if isinstance(current_user, User) else current_user['id']
    return await credit_service.get_transaction_history(
        user_id=user_id,
        skip=skip,
        limit=limit
    )


# New endpoints for plans and subscriptions

@router.get(
    "/plans",
    response_model=plan_schemas.PlanListResponse,
    response_class=DecimalJSONResponse
)
async def list_plans(
    db: AsyncSession = Depends(get_db)
):
    """
    List all available plans.

    Args:
        db: Database session

    Returns:
        PlanListResponse: List of available plans
    """
    try:
        credit_service = CreditService(db)
        plans = await credit_service.get_all_active_plans()
        return plan_schemas.PlanListResponse(
            plans=plans,
            count=len(plans)
        )
    except Exception as e:
        logger.error(f"Error listing plans: {str(e)}", 
                   event_type="plan_list_error", 
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving plans"
        )


@router.post(
    "/plans/purchase",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def purchase_plan(
    request: plan_schemas.PlanPurchaseRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Purchase a plan and set up a subscription.

    Args:
        request: Plan purchase details
        background_tasks: FastAPI background tasks
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        # Process payment (mock)
        logger.info(f"Processing payment for plan: {request.plan_id}", 
                  event_type="plan_payment_processing",
                  user_id=user_id,
                  plan_id=request.plan_id,
                  payment_method_id=request.payment_method_id,
                  reference_id=request.reference_id)
        
        # Purchase plan
        transaction, subscription = await credit_service.purchase_plan(
            user_id=user_id,
            plan_id=request.plan_id,
            reference_id=request.reference_id,
            background_tasks=background_tasks
        )
        
        logger.info(f"Plan purchased successfully", 
                  event_type="plan_purchased",
                  user_id=user_id,
                  plan_id=request.plan_id,
                  transaction_id=transaction.id,
                  subscription_id=subscription.id)
                  
        return transaction
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(f"Error purchasing plan: {str(e)}",
                   event_type="plan_purchase_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   plan_id=request.plan_id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error purchasing plan: {str(e)}"
        )


@router.post(
    "/plans/upgrade",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def upgrade_plan(
    request: plan_schemas.PlanUpgradeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upgrade to a higher tier plan.

    Args:
        request: Plan upgrade details
        background_tasks: FastAPI background tasks
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details for the additional credits
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        # Process payment (mock)
        logger.info(f"Processing payment for plan upgrade", 
                  event_type="plan_upgrade_payment_processing",
                  user_id=user_id,
                  current_subscription_id=request.current_subscription_id,
                  new_plan_id=request.new_plan_id,
                  payment_method_id=request.payment_method_id,
                  reference_id=request.reference_id)
        
        # Upgrade plan
        transaction, subscription = await credit_service.upgrade_plan(
            user_id=user_id,
            current_subscription_id=request.current_subscription_id,
            new_plan_id=request.new_plan_id,
            reference_id=request.reference_id,
            background_tasks=background_tasks
        )
        
        logger.info(f"Plan upgraded successfully", 
                  event_type="plan_upgraded",
                  user_id=user_id,
                  new_plan_id=request.new_plan_id,
                  new_subscription_id=subscription.id if subscription else None)
                  
        return transaction
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(f"Error upgrading plan: {str(e)}",
                   event_type="plan_upgrade_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   current_subscription_id=request.current_subscription_id,
                   new_plan_id=request.new_plan_id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error upgrading plan: {str(e)}"
        )


@router.post(
    "/one-time-purchase",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def purchase_one_time_credits(
    request: plan_schemas.OneTimePurchaseRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Purchase credits as a one-time transaction (no subscription).

    Args:
        request: One-time purchase details
        background_tasks: FastAPI background tasks
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        # Process payment (mock)
        logger.info(f"Processing payment for one-time credits", 
                  event_type="one_time_payment_processing",
                  user_id=user_id,
                  credit_amount=request.credit_amount,
                  price=request.price,
                  payment_method_id=request.payment_method_id,
                  reference_id=request.reference_id)
        
        # Purchase credits
        transaction = await credit_service.purchase_one_time_credits(
            user_id=user_id,
            amount=request.credit_amount,
            price=request.price,
            reference_id=request.reference_id,
            background_tasks=background_tasks
        )
        
        logger.info(f"One-time credits purchased successfully", 
                  event_type="one_time_credits_purchased",
                  user_id=user_id,
                  credit_amount=request.credit_amount,
                  transaction_id=transaction.id)
                  
        return transaction
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(f"Error purchasing one-time credits: {str(e)}",
                   event_type="one_time_purchase_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   credit_amount=request.credit_amount,
                   price=request.price,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error purchasing one-time credits: {str(e)}"
        )


@router.get(
    "/subscriptions",
    response_model=plan_schemas.SubscriptionListResponse,
    response_class=DecimalJSONResponse
)
async def get_user_subscriptions(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's subscriptions.

    Args:
        include_inactive: Whether to include inactive subscriptions
        current_user: Authenticated user
        db: Database session

    Returns:
        SubscriptionListResponse: List of user's subscriptions
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        subscriptions = await credit_service.get_user_subscriptions(
            user_id=user_id,
            include_inactive=include_inactive
        )
        
        return plan_schemas.SubscriptionListResponse(
            subscriptions=subscriptions,
            count=len(subscriptions)
        )
        
    except Exception as e:
        logger.error(f"Error fetching subscriptions: {str(e)}",
                   event_type="subscription_fetch_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching subscriptions: {str(e)}"
        )


@router.put(
    "/subscriptions/{subscription_id}/auto-renew",
    response_model=plan_schemas.SubscriptionResponse,
    responses={
        200: {"description": "Auto-renewal setting updated"},
        404: {"description": "Subscription not found"}
    }
)
async def update_auto_renew(
    subscription_id: int,
    auto_renew: bool,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update auto-renewal setting for a subscription.

    Args:
        subscription_id: ID of the subscription
        auto_renew: New auto-renewal setting
        current_user: Authenticated user
        db: Database session

    Returns:
        SubscriptionResponse: Updated subscription details
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        # Check if subscription belongs to user
        subscription = await credit_service.get_subscription_by_id(subscription_id)
        
        if not subscription or subscription.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )
            
        # Update auto-renewal setting
        updated_subscription = await credit_service.update_subscription_auto_renew(
            subscription_id=subscription_id,
            auto_renew=auto_renew
        )
        
        logger.info(f"Subscription auto-renewal updated", 
                  event_type="subscription_auto_renew_updated",
                  user_id=user_id,
                  subscription_id=subscription_id,
                  auto_renew=auto_renew)
                  
        return updated_subscription
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(f"Error updating subscription auto-renewal: {str(e)}",
                   event_type="subscription_update_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   subscription_id=subscription_id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating subscription auto-renewal: {str(e)}"
        )


@router.put(
    "/subscriptions/{subscription_id}/cancel",
    response_model=plan_schemas.SubscriptionResponse,
    responses={
        200: {"description": "Subscription cancelled"},
        404: {"description": "Subscription not found"}
    }
)
async def cancel_subscription(
    subscription_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel a subscription.
    
    The subscription will remain active until the end of the current billing period,
    but will not auto-renew.

    Args:
        subscription_id: ID of the subscription
        current_user: Authenticated user
        db: Database session

    Returns:
        SubscriptionResponse: Updated subscription details
    """
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        credit_service = CreditService(db)
        
        # Check if subscription belongs to user
        subscription = await credit_service.get_subscription_by_id(subscription_id)
        
        if not subscription or subscription.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )
            
        # Cancel subscription (sets auto_renew to false)
        updated_subscription = await credit_service.update_subscription_auto_renew(
            subscription_id=subscription_id,
            auto_renew=False
        )
        
        logger.info(f"Subscription cancelled", 
                  event_type="subscription_cancelled",
                  user_id=user_id,
                  subscription_id=subscription_id)
                  
        return updated_subscription
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(f"Error cancelling subscription: {str(e)}",
                   event_type="subscription_cancel_error",
                   user_id=current_user.id if isinstance(current_user, User) else current_user['id'],
                   subscription_id=subscription_id,
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling subscription: {str(e)}"
        )