"""Router module for user profile and session management endpoints."""

from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta, datetime, timezone

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.auth_schemas import RefreshToken, Token, UserResponse
from app.models.user import User
from app.core.auth import get_current_user, get_current_active_user
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