"""Router module for email verification endpoints."""

from datetime import datetime, UTC, timedelta, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.auth_schemas import ResendVerification, VerifyEmail
from app.services.user_service import UserService
from app.services.email_service import EmailService
from app.models.user import User, EmailVerificationToken
from app.log.logging import logger

router = APIRouter()

@router.get(
    "/verify-email",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Email successfully verified"},
        400: {"description": "Invalid or expired verification token"}
    }
)
async def verify_email(
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Verify user's email using the token sent via email.
    
    Args:
        token: The verification token from query parameter
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Dict containing success message
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Find the token record first
        result = await db.execute(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token == token)
            .where(EmailVerificationToken.used == False)  # noqa: E712
        )
        token_record = result.scalar_one_or_none()
        
        if not token_record:
            logger.warning(
                "Invalid verification token attempt",
                event_type="email_verification_error",
                token=token,
                error="invalid_token"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token"
            )
            
        # Check if token is expired
        # Ensure both datetimes are timezone-aware for comparison
        current_time = datetime.now(UTC)
        expires_at = token_record.expires_at
        if not expires_at.tzinfo:
            # If expires_at is naive, make it aware with UTC timezone
            expires_at = expires_at.replace(tzinfo=UTC)
        
        if current_time > expires_at:
            logger.warning(
                "Expired verification token attempt",
                event_type="email_verification_error",
                token=token,
                error="expired_token"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token has expired"
            )
            
        # Get user and verify email
        result = await db.execute(
            select(User).where(User.id == token_record.user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(
                "User not found for verification token",
                event_type="email_verification_error",
                token=token,
                user_id=token_record.user_id
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification token"
            )
            
        # Update user verification status
        user.is_verified = True
        token_record.used = True
        await db.commit()
            
        # Try to send welcome email, but don't fail verification if it fails
        try:
            email_service = EmailService(background_tasks, db)
            await email_service.send_welcome_email(user)
        except Exception as e:
            logger.error(
                "Failed to send welcome email",
                event_type="welcome_email_error",
                user_id=user.id,
                email=user.email,
                error=str(e)
            )
            # Continue with verification even if welcome email fails
            
        logger.info(
            "Email verification successful",
            event_type="email_verified",
            user_id=user.id,
            email=user.email
        )
        
        # Generate a token for immediate login
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
        # Create token - always use email as subject for new tokens
        access_token = create_access_token(
            data={
                "sub": user.email,  # Always use email as subject for new tokens
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        
        response_data = {
            "message": "Email verified successfully",
            "email": str(user.email),
            "is_verified": True,
            "access_token": access_token,
            "token_type": "bearer",
            "detail": {
                "message": "Email verified successfully"
            }
        }
        return response_data
        
    except HTTPException as http_ex:
        logger.error(
            "Email verification failed",
            event_type="email_verification_error",
            token=token,
            error=str(http_ex.detail)
        )
        raise http_ex
        
    except Exception as e:
        logger.error(
            "Email verification error",
            event_type="email_verification_error",
            token=token,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to verify email"
        )


@router.post(
    "/resend-verification",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Verification email resent"},
        404: {"description": "User not found"}
    }
)
async def resend_verification_email(
    request: ResendVerification,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Resend verification email to a user.
    
    Args:
        request: Contains the email address
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Dict containing success message
    """
    try:
        # Get user by email
        user_service = UserService(db)
        user = await user_service.get_user_by_email(str(request.email))
        
        if not user:
            # For security, don't reveal if the email exists or not
            return {
                "message": "If your email is registered, a verification link has been sent."
            }
            
        # Check if already verified
        if user.is_verified:
            return {
                "message": "Email is already verified."
            }
            
        # Send verification email
        sent = await user_service.send_verification_email(user, background_tasks)
        
        logger.info(
            "Verification email resent",
            event_type="verification_email_resent",
            user_id=user.id,
            email=str(user.email),
            success=sent
        )
        
        return {
            "message": "Verification email has been resent."
        }
        
    except Exception as e:
        logger.error(
            "Error resending verification email",
            event_type="resend_verification_error",
            email=str(request.email),
            error_type=type(e).__name__,
            error_details=str(e)
        )
        # For security, don't reveal specific errors
        return {
            "message": "If your email is registered, a verification link has been sent."
        }