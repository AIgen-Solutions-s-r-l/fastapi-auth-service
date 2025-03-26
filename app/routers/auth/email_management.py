"""Router module for email management endpoints."""

from datetime import datetime, timezone, timedelta, UTC
from typing import Dict, Any, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.user import User, EmailChangeRequest
from app.services.user_service import UserService
from app.services.email_service import EmailService
from app.schemas.auth_schemas import EmailChange
from app.core.auth import get_current_active_user
from app.log.logging import logger

router = APIRouter()

@router.put(
    "/users/change-email",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Email change request created and verification email sent",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Verification email sent to your new email address",
                        "email": "new.email@example.com",
                        "verification_sent": True
                    }
                }
            }
        },
        400: {"description": "Email already registered"},
        401: {"description": "Invalid password or unauthorized"},
        404: {"description": "User not found"}
    }
)
async def change_email(
    email_change: EmailChange,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Request to change user's email address.
    
    Creates an email change request and sends a verification email to the new address.
    The email will only be updated after verification of the new address.

    Args:
        email_change: New email and current password
        background_tasks: FastAPI background tasks
        db: Database session
        current_user: Authenticated and verified user

    Returns:
        Dict containing success message and verification status

    Raises:
        HTTPException: If authentication fails, email is taken, or user not found
    """
    try:
        # Initialize user service
        user_service = UserService(db)

        # Verify current password first
        try:
            if not verify_password(email_change.current_password, str(current_user.hashed_password)):
                logger.error(
                    "Invalid password for email change",
                    event_type="email_change_error",
                    email=current_user.email,
                    error_type="invalid_password"
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid password"
                )
        except (TypeError, AttributeError) as e:
            logger.error(
                "Password verification error",
                event_type="email_change_error",
                email=current_user.email,
                error_type=type(e).__name__,
                error_details=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password format"
            )

        # Check if new email already exists
        existing_user = await user_service.get_user_by_email(str(email_change.new_email))
        if existing_user and existing_user.id != current_user.id:
            logger.error(
                "Email already registered",
                event_type="email_change_error",
                email=current_user.email,
                new_email=str(email_change.new_email),
                error_type="email_exists"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create email change request
        success, message, change_request = await user_service.create_email_change_request(
            current_user,
            str(email_change.new_email),
            email_change.current_password
        )
        
        if not success:
            logger.error(
                "Failed to create email change request",
                event_type="email_change_error",
                email=current_user.email,
                new_email=str(email_change.new_email),
                error=message
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=message
            )

        # Send verification email to the new address
        email_service = EmailService(background_tasks, db)
        await email_service.send_email_change_verification(
            current_user,
            str(email_change.new_email),
            change_request.token
        )

        logger.info(
            "Email change request created",
            event_type="email_change_requested",
            user_id=current_user.id,
            old_email=current_user.email,
            new_email=str(email_change.new_email)
        )

        return {
            "message": "Verification email sent to your new email address. Please check your inbox and click the verification link to complete the email change.",
            "email": str(email_change.new_email),
            "verification_sent": True
        }

    except JWTError as e:
        # Handle JWT authentication errors
        logger.error(
            "Email change failed - invalid token",
            event_type="email_change_error",
            error_type="JWTError",
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        ) from e
    except HTTPException as e:
        # Re-raise HTTP exceptions from the service layer
        raise e
    except Exception as e:
        logger.error(
            "Email change failed",
            event_type="email_change_error",
            email=current_user.email,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing email change request"
        ) from e


@router.get(
    "/verify-email-change",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Email successfully changed and verified"},
        400: {"description": "Invalid or expired verification token"}
    }
)
async def verify_email_change(
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Verify and complete an email change request using the token sent via email.
    
    Args:
        token: The verification token from query parameter
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Dict containing success message and new access token
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Initialize user service
        user_service = UserService(db)
        
        # Verify the email change token
        success, message, updated_user = await user_service.verify_email_change(token)
        
        if not success or not updated_user:
            logger.error(
                "Email change verification failed",
                event_type="email_change_verification_error",
                token=token,
                error=message
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message
            )
        
        # Send confirmation emails
        email_service = EmailService(background_tasks, db)
        
        # Get the old email from the change request
        result = await db.execute(
            select(EmailChangeRequest)
            .where(EmailChangeRequest.token == token)
        )
        change_request = result.scalar_one_or_none()
        
        if change_request:
            # Send confirmation emails to both old and new addresses
            await email_service.send_email_change_confirmation(
                updated_user,
                change_request.current_email
            )
        
        # Generate a token for immediate login with the new email
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
        # Create token with the new email
        access_token = create_access_token(
            data={
                "sub": updated_user.email,
                "id": updated_user.id,
                "is_admin": updated_user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        
        logger.info(
            "Email change verification successful",
            event_type="email_change_verified",
            user_id=updated_user.id,
            email=updated_user.email
        )
        
        return {
            "message": "Email address successfully changed and verified",
            "email": str(updated_user.email),
            "is_verified": True,
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
        
    except Exception as e:
        logger.error(
            "Email change verification error",
            event_type="email_change_verification_error",
            token=token,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to verify email change"
        )