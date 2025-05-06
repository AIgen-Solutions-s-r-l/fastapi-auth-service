"""Router module for user profile and session management endpoints."""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta, datetime, timezone

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.auth_schemas import (
    RefreshToken,
    Token,
    UserResponse,
    UserStatusResponse,
    # SubscriptionStatusResponse # No longer needed here, will be in subscription_schemas
)
from app.schemas.subscription_schemas import (
    SubscriptionCancelRequest,
    SubscriptionCancelResponse,
    ErrorResponse as SubscriptionErrorResponse # Alias to avoid conflict if other ErrorResponse exists
)
from app.models.user import User
from app.core.auth import get_current_user, get_current_active_user
from app.services.user_service import UserService
from app.services.stripe_service import StripeService # For Stripe interactions
from app.log.logging import logger

router = APIRouter()

@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        200: {"description": "Current user profile retrieved successfully"},
        401: {"description": "Not authenticated"}
    }
)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
) -> UserResponse:
    """
    Get the current authenticated user's profile.
    
    Args:
        current_user: The authenticated user from the token
        
    Returns:
        UserResponse: User profile data
    """
    logger.info(
        "User profile retrieved",
        event_type="profile_retrieved",
        user_id=current_user.id,
        email=current_user.email
    )
    
    return UserResponse(
        email=current_user.email,
        is_verified=current_user.is_verified,
        auth_type=current_user.auth_type
    )

@router.get(
    "/me/status",
    response_model=UserStatusResponse,
    summary="Get current user's status, subscription, and credits",
    tags=["User"],
    responses={
        200: {"description": "Successfully retrieved user status"},
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"}
    }
)
async def get_user_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> UserStatusResponse:
    """
    Fetches the current authenticated user's account status, 
    subscription details (if any), and credit balance.
    """
    user_service = UserService(db)
    user_status_data = await user_service.get_user_status_details(user_id=current_user.id)

    if not user_status_data:
        logger.warning(
            "User status not found for user", 
            event_type="user_status_not_found",
            user_id=current_user.id
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User status details not found")

    logger.info(
        "User status retrieved",
        event_type="user_status_retrieved",
        user_id=current_user.id
    )
    return user_status_data


@router.post(
    "/refresh",
    response_model=Token,
    responses={
        200: {"description": "Token refreshed successfully"},
        401: {"description": "Invalid or expired token"}
    }
)
async def refresh_token(
    refresh_request: RefreshToken,
    db: AsyncSession = Depends(get_db)
) -> Token:
    """
    Refresh a JWT token.
    
    Args:
        refresh_request: Contains the token to refresh
        db: Database session
        
    Returns:
        Token: New access token
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Get the user from the token
        current_user = await get_current_user(token=refresh_request.token, db=db)
        
        # Generate a new token
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
        access_token = create_access_token(
            data={
                "sub": current_user.email,
                "id": current_user.id,
                "is_admin": current_user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        
        logger.info(
            "Token refreshed",
            event_type="token_refreshed",
            user_id=current_user.id,
            email=current_user.email
        )
        
        return Token(access_token=access_token, token_type="bearer")
        
    except Exception as e:
        logger.error(
            "Token refresh failed",
            event_type="token_refresh_error",
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

@router.post(
    "/logout",
    responses={
        200: {"description": "Successfully logged out"}
    }
)
async def logout(
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Log out the current user.
    
    Note: Since JWT tokens are stateless, this endpoint doesn't actually invalidate the token.
    In a real implementation, you might want to add the token to a blacklist or use Redis to track logged out tokens.
    
    Args:
        current_user: The authenticated user
        
    Returns:
        Dict with success message
    """
    logger.info(
        "User logged out",
        event_type="user_logout",
        user_id=current_user.id,
        email=current_user.email
    )
    
    return {"message": "Successfully logged out"}


@router.post(
    "/me/subscription/cancel",
    response_model=SubscriptionCancelResponse,
    summary="Cancel the current user's active subscription",
    tags=["Subscription"], # New tag for subscription related endpoints
    responses={
        200: {"description": "Subscription cancellation initiated successfully"},
        400: {"description": "Bad Request (e.g., no subscription to cancel, already canceled)", "model": SubscriptionErrorResponse},
        401: {"description": "Unauthorized", "model": SubscriptionErrorResponse},
        404: {"description": "Active subscription not found", "model": SubscriptionErrorResponse},
        500: {"description": "Internal Server Error (e.g., failed to communicate with Stripe)", "model": SubscriptionErrorResponse},
    }
)
async def cancel_subscription(
    request: SubscriptionCancelRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
) -> SubscriptionCancelResponse:
    """
    Initiates the cancellation of the current user's active Stripe subscription.
    This typically sets `cancel_at_period_end` to true on Stripe.
    """
    logger.info(
        "Subscription cancellation request received",
        event_type="subscription_cancel_request",
        user_id=current_user.id,
        reason=request.reason
    )

    stripe_service = StripeService(db_session=db) # Assuming StripeService needs db session
    
    try:
        # The service method will handle fetching user's subscription,
        # interacting with Stripe, and updating local records if necessary.
        cancellation_details = await stripe_service.cancel_user_subscription(
            user_id=current_user.id,
            reason=request.reason
        )
        
        logger.info(
            "Subscription cancellation processed successfully",
            event_type="subscription_cancel_success",
            user_id=current_user.id,
            stripe_subscription_id=cancellation_details.get("stripe_subscription_id"),
            new_status=cancellation_details.get("subscription_status")
        )
        
        return SubscriptionCancelResponse(
            message=f"Subscription cancellation initiated successfully. Access remains until {cancellation_details.get('period_end_date', 'the end of the current period')}.",
            subscription_status=cancellation_details.get("subscription_status", "unknown")
        )

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions directly (e.g., 404 if no active subscription)
        logger.warning(
            "Subscription cancellation failed with HTTPException",
            event_type="subscription_cancel_http_error",
            user_id=current_user.id,
            status_code=http_exc.status_code,
            detail=http_exc.detail
        )
        raise http_exc
    except Exception as e:
        logger.error(
            "Subscription cancellation failed with an unexpected error",
            event_type="subscription_cancel_unexpected_error",
            user_id=current_user.id,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while canceling the subscription."
        )