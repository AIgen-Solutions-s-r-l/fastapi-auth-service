"""Router module for password management endpoints."""

from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
from app.schemas.auth_schemas import PasswordChange, PasswordResetRequest, PasswordReset
from app.models.user import User
from app.services.user_service import UserService
from app.core.auth import get_current_active_user
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