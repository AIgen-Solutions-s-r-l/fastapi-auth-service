"""Router module for authentication-related endpoints including login, registration, and password management."""

from datetime import timedelta, datetime, timezone, UTC
from typing import Dict, Any, Optional
from jose import jwt, JWTError
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import EmailVerificationToken, EmailChangeRequest
from app.core.database import get_db
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token, verify_jwt_token, verify_password
from app.core.auth import get_current_user, get_current_active_user, get_internal_service
from app.schemas.auth_schemas import (
    LoginRequest, Token, UserCreate, PasswordChange,
    PasswordResetRequest, PasswordReset, RefreshToken, EmailChange,
    VerifyEmail, ResendVerification, UserResponse, RegistrationResponse,
    GoogleAuthRequest, GoogleAuthCallback, AccountLinkRequest
)
from app.services.user_service import (
    create_user, authenticate_user, update_user_password, delete_user,
    create_password_reset_token, verify_reset_token, reset_password,
    get_user_by_email, UserService
)
from app.models.user import User
from app.log.logging import logger
from app.core.email import send_email
from app.core.config import settings
from app.services.email_service import EmailService
from app.services.oauth_service import GoogleOAuthService
from app.core.config import settings


router = APIRouter(tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@router.post(
    "/login",
    response_model=Token,
    description="Authenticate user and return JWT token",
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"}
    }
)
async def login(
        credentials: LoginRequest,
        db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        # Only use email for authentication
        email = credentials.email
        
        user = await authenticate_user(db, email, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", email=email, reason="invalid_credentials")
            raise InvalidCredentialsError()
            
        # Check if user's email is verified
        if not user.is_verified:
            logger.warning("Login attempt by unverified user", event_type="login_failed", email=email, reason="unverified_user")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please check your email for verification instructions."
            )

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Use email as the subject for tokens
        access_token = create_access_token(
            data={
                "sub": user.email,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", email=user.email)
        return Token(access_token=access_token, token_type="bearer")
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error("Login error", event_type="login_error", email=credentials.email, error_type=type(e).__name__, error_details=str(e))
        raise InvalidCredentialsError() from e


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegistrationResponse,
    responses={
        201: {
            "description": "User successfully registered",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User registered successfully",
                        "email": "john@example.com",
                        "verification_sent": True
                    }
                }
            }
        },
        409: {"description": "Email already exists"}
    }
)
async def register_user(
        user: UserCreate,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db)
) -> RegistrationResponse:
    """
    Register a new user and send a verification email.

    Returns:
        RegistrationResponse containing:
        - success message
        - email
        - verification_sent status
    """
    try:
        # Create the user (initially not verified)
        new_user = await create_user(db, str(user.email), user.password)
        
        # Send verification email
        user_service = UserService(db)
        verification_sent = await user_service.send_verification_email(new_user, background_tasks)

        logger.info("User registered",
                  event_type="user_registered",
                  email=str(user.email),
                  verification_sent=verification_sent)

        return RegistrationResponse(
            message="User registered successfully. Please check your email to verify your account.",
            email=str(new_user.email),
            verification_sent=verification_sent
        )
        
    except UserAlreadyExistsError as e:
        logger.error("Registration failed",
                   event_type="registration_error",
                   email=str(user.email),
                   error_type="user_exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "User already exists", "detail": str(e)}
        ) from e


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


@router.get(
    "/users/by-email/{email}",
    response_model=UserResponse,
    include_in_schema=False,  # Hide from public API docs
    responses={
        200: {"description": "User details retrieved successfully"},
        403: {"description": "Forbidden - Internal service access only"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        email: str,
        service_id: str = Depends(get_internal_service),
        db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Retrieve user details by email.
    
    This is an internal-only endpoint for service-to-service communication.
    Requires a valid INTERNAL_API_KEY header.
    """
    try:
        user = await get_user_by_email(db, email)
        logger.info(
            "User details retrieved",
            event_type="internal_endpoint_access",
            email=email,
            service_id=service_id
        )
        if user is None:
            logger.error(
                "User object is None",
                event_type="internal_endpoint_error",
                email=email,
                service_id=service_id
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        return UserResponse(
            email=user.email,
            is_verified=user.is_verified
        )
        
    except UserNotFoundError as e:
        logger.error(
            "User lookup failed",
            event_type="internal_endpoint_error",
            email=email,
            error_type="user_not_found",
            service_id=service_id
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


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


@router.get(
    "/verify-email-templates",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Template verification results"}
    }
)
async def verify_email_templates(
    db: AsyncSession = Depends(get_db)
):
    """
    Verify that all email templates exist and can be rendered.
    """
    results = {}
    
    # Create email service
    email_service = EmailService(BackgroundTasks(), db)
    
    # Test registration confirmation template
    results["registration_confirmation"] = email_service.verify_template(
        "registration_confirmation",
        {
            "verification_link": "https://example.com/verify?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test welcome template
    results["welcome"] = email_service.verify_template(
        "welcome",
        {
            "login_link": "https://example.com/login"
        }
    )
    
    # Test password change request template
    results["password_change_request"] = email_service.verify_template(
        "password_change_request",
        {
            "reset_link": "https://example.com/reset?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test password change confirmation template
    results["password_change_confirmation"] = email_service.verify_template(
        "password_change_confirmation",
        {
            "login_link": "https://example.com/login",
            "ip_address": "127.0.0.1",
            "time": "2025-02-26 11:30:00 UTC"
        }
    )
    
    # Test email change verification template
    results["email_change_verification"] = email_service.verify_template(
        "email_change_verification",
        {
            "email": "new.email@example.com",
            "verification_link": "https://example.com/verify-email-change?token=test_token",
            "hours_valid": 24
        }
    )
    
    # Test email change confirmation template
    results["email_change_confirmation"] = email_service.verify_template(
        "email_change_confirmation",
        {
            "email": "new.email@example.com",
            "login_link": "https://example.com/login",
            "ip_address": "127.0.0.1",
            "time": "2025-02-26 11:30:00 UTC"
        }
    )
    
    # Test one time credit purchase template
    results["one_time_credit_purchase"] = email_service.verify_template(
        "one_time_credit_purchase",
        {
            "amount": 50.0,
            "credits": 100.0,
            "purchase_date": "2025-02-26 11:30:00",
            "dashboard_link": "https://example.com/dashboard"
        }
    )
    
    # Test plan upgrade template
    results["plan_upgrade"] = email_service.verify_template(
        "plan_upgrade",
        {
            "old_plan": "Basic",
            "new_plan": "Premium",
            "additional_credits": 200.0,
            "upgrade_date": "2025-02-26 11:30:00",
            "renewal_date": "2025-03-26 11:30:00",
            "dashboard_link": "https://example.com/dashboard"
        }
    )
    
    return {
        "message": "Template verification completed",
        "results": results
    }
