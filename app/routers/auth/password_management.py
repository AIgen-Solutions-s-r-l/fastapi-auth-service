"""Router module for password management endpoints."""

from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt

from app.core.database import get_db
from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
from app.schemas.auth_schemas import PasswordChange, PasswordResetRequest, PasswordReset
from app.models.user import User
from app.services.user_service import UserService, create_password_reset_token, verify_reset_token, reset_password
from app.services.email_service import EmailService
from app.core.auth import get_current_active_user
from app.core.config import settings
from app.log.logging import logger

router = APIRouter()

@router.put(
    "/users/password",
    responses={
        200: {"description": "Password successfully updated"},
        401: {"description": "Invalid current password"},
        404: {"description": "User not found"}
    }
)
async def change_password(
        passwords: PasswordChange,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
) -> Dict[str, str]:
    """
    Change user password and send confirmation email.

    Requires authentication, verification, and validation of current password.
    """
    try:
        # Explicitly check for empty new password
        if not passwords.new_password or len(passwords.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must be at least 8 characters long"
            )
            
        # Update password
        user_service = UserService(db)
        success = await user_service.update_user_password(
            current_user.email,
            passwords.current_password,
            passwords.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
            
        # Send confirmation email
        await user_service.send_password_change_confirmation(current_user, background_tasks)
        
        logger.info("Password changed", event_type="password_changed", email=current_user.email)
        return {"message": "Password updated successfully"}
        
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("Password change failed", event_type="password_change_error", email=current_user.email, error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        ) from e
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions without changing status code
        logger.error(f"HTTP exception in change_password: {http_ex.status_code}: {http_ex.detail}",
                    event_type="password_change_error",
                    error_type="HTTPException",
                    error_details=str(http_ex.detail))
        raise http_ex
    except Exception as e:
        logger.error(f"Unhandled exception in change_password: {type(e).__name__}: {str(e)}",
                    event_type="debug_password_change_error",
                    error_type=type(e).__name__,
                    error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error changing password: {str(e)}"
        ) from e

    
@router.post(
    "/password-reset-request",
    responses={
        200: {"description": "Password reset link sent if account exists"}
    }
)
async def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Request a password reset link to be sent via email."""
    try:
        token = await create_password_reset_token(db, request.email)
        # Use the correct endpoint for password reset
        reset_link = f"{settings.FRONTEND_URL}/update-password?token={token}"

        # Create email service
        email_service = EmailService(background_tasks, db)
        
        # Get user for email
        user_service = UserService(db)
        user = await user_service.get_user_by_email(str(request.email))
        
        if user:
            # Log the reset link for debugging
            logger.info(
                "Generated password reset link",
                event_type="password_reset_link_generated",
                email=str(request.email),
                reset_link=reset_link
            )
            await email_service.send_password_change_request(user, token)

        logger.info(
            "Password reset requested",
            event_type="password_reset_requested",
            email=str(request.email)
        )

        return {"message": "Password reset link sent to email if account exists"}
    except (UserNotFoundError, ValueError, jwt.JWTError, HTTPException) as e:
        logger.error("Password reset request failed", event_type="password_reset_request_error", email=request.email, error=str(e))
        # Return same message to prevent email enumeration, even on HTTPException
        return {"message": "Password reset link sent to email if account exists"}


@router.post(
    "/password-reset",
    responses={
        200: {"description": "Password successfully reset"},
        400: {"description": "Invalid or expired token"},
        404: {"description": "User not found"}
    }
)
async def reset_password_with_token(
    reset_data: PasswordReset,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Reset a user's password using a valid reset token."""
    try:
        # Verify token and get user ID
        user_id = await verify_reset_token(db, reset_data.token)
        
        # Reset the password
        success = await reset_password(db, user_id, reset_data.new_password)
        
        if not success:
            logger.error(
                "Password reset failed",
                event_type="password_reset_error",
                token=reset_data.token,
                error="Database update failed"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to reset password"
            )
            
        # Get user for confirmation email
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            # Send confirmation email
            email_service = EmailService(background_tasks, db)
            await email_service.send_password_reset_confirmation(user)
            
            logger.info(
                "Password reset successful",
                event_type="password_reset_success",
                user_id=user_id,
                email=user.email
            )
        
        return {"message": "Password has been reset successfully"}
        
    except ValueError as e:
        logger.error(
            "Password reset failed - invalid user/token",
            event_type="password_reset_error",
            token=reset_data.token,
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user or invalid/expired token"
        )
    except Exception as e:
        logger.error(
            "Password reset failed",
            event_type="password_reset_error",
            token=reset_data.token,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing password reset"
        )
