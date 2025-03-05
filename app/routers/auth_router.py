"""Router module for authentication-related endpoints including login, registration, and password management."""

from datetime import timedelta, datetime, timezone
from typing import Dict, Any, Optional
from jose import jwt, JWTError
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token, verify_jwt_token, verify_password
from app.core.auth import get_current_user
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


@router.post(
    "/verify-email",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Email successfully verified"},
        400: {"description": "Invalid or expired verification token"}
    }
)
async def verify_email(
    verification: VerifyEmail,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Verify user's email using the token sent via email.
    
    Args:
        verification: Contains the verification token
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Dict containing success message
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        user_service = UserService(db)
        success, user = await user_service.verify_email(verification.token)
        
        if not success or not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
            
        # Send welcome email
        email_service = EmailService(background_tasks, db)
        await email_service.send_welcome_email(user)
        
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
        
        return {
            "message": "Email verified successfully",
            "email": str(user.email),
            "is_verified": True,
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException as http_ex:
        logger.error(
            "Email verification failed",
            event_type="email_verification_error",
            token=verification.token,
            error=str(http_ex.detail)
        )
        raise http_ex
        
    except Exception as e:
        logger.error(
            "Email verification error",
            event_type="email_verification_error",
            token=verification.token,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying email: {str(e)}"
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
    responses={
        200: {"description": "User details retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        email: str,
        db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Retrieve user details by email."""
    try:
        user = await get_user_by_email(db, email)
        logger.info("User details retrieved", event_type="user_details_retrieved", email=email)
        if user is None:
            logger.error("User object is None", event_type="user_lookup_error", email=email)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        return UserResponse(
            email=user.email,
            is_verified=user.is_verified
        )
        
    except UserNotFoundError as e:
        logger.error("User lookup failed", event_type="user_lookup_error", email=email, error_type="user_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.put(
    "/users/change-email",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Email successfully updated",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Email updated successfully",
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
    token: str = Depends(oauth2_scheme)
) -> Dict[str, Any]:
    """
    Change user's email address and send verification.

    Requires authentication and current password verification.
    The new email must not be already registered by another user.

    Args:
        email_change: Current email, new email and current password
        background_tasks: FastAPI background tasks
        db: Database session
        token: JWT token for authentication

    Returns:
        Dict containing success message and updated user info

    Raises:
        HTTPException: If authentication fails, email is taken, or user not found
    """
    try:
        # Verify JWT token and check if user is authorized
        payload = verify_jwt_token(token)
        token_subject = payload.get("sub")
        
        # Get user from token
        user_service = UserService(db)
        token_user = await user_service.get_user_by_email(token_subject)
            
        if not token_user:
            logger.error(
                "User not found for token",
                event_type="email_change_error",
                email=token_subject,
                error_type="user_not_found"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verify current password first
        try:
            if not verify_password(email_change.current_password, str(token_user.hashed_password)):
                logger.error(
                    "Invalid password for email change",
                    event_type="email_change_error",
                    email=token_subject,
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
                email=token_subject,
                error_type=type(e).__name__,
                error_details=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password format"
            )

        # Only allow users to change their own email
        if token_user.email != token_subject:
            logger.error(
                "Unauthorized email change attempt",
                event_type="email_change_error",
                email=token_subject,
                attempted_email=token_user.email,
                error_type="unauthorized"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authorized to change this email"
            )

        # Check if new email already exists
        existing_user = await user_service.get_user_by_email(str(email_change.new_email))
        if existing_user:
            logger.error(
                "Email already registered",
                event_type="email_change_error",
                email=token_subject,
                new_email=str(email_change.new_email),
                error_type="email_exists"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Update email through service
        try:
            updated_user = await user_service.update_user_email(
                token_subject,
                email_change.current_password,
                str(email_change.new_email)
            )
        except Exception as e:
            logger.error(
                "Failed to update email",
                event_type="email_change_error",
                email=token_subject,
                new_email=str(email_change.new_email),
                error_type=type(e).__name__,
                error_details=str(e)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update email"
            )

        # Send verification email for new email address
        verification_sent = await user_service.send_verification_email(updated_user, background_tasks)

        # Create a new token with the updated email
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
        # Create new access token with updated email
        access_token = create_access_token(
            data={
                "sub": updated_user.email,  # Use the new email
                "id": updated_user.id,
                "is_admin": updated_user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info(
            "Email changed successfully",
            event_type="email_changed",
            old_email=token_subject,
            new_email=str(email_change.new_email),
            verification_sent=verification_sent
        )

        return {
            "message": "Email updated successfully. Please verify your new email address.",
            "email": str(updated_user.email),
            "verification_sent": verification_sent,
            "access_token": access_token,
            "token_type": "bearer"
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
            email=token_subject,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating email"
        ) from e

@router.put(
    "/users/change-password",
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
        token: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Change user password and send confirmation email.

    Requires authentication and verification of current password.
    """
    try:
        # Get user email from token
        payload = verify_jwt_token(token)
        email = payload.get("sub")
        
        # Explicitly check for empty new password
        if not passwords.new_password or len(passwords.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="New password must be at least 8 characters long"
            )
            
        # Update password
        user_service = UserService(db)
        success = await user_service.update_user_password(
            email,
            passwords.current_password,
            passwords.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
            
        # Get user for email notification
        user = await user_service.get_user_by_email(email)
        if user:
            # Send confirmation email
            await user_service.send_password_change_confirmation(user, background_tasks)
        
        logger.info("Password changed", event_type="password_changed", email=email)
        return {"message": "Password updated successfully"}
        
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("Password change failed", event_type="password_change_error", email=email, error_type=type(e).__name__)
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


@router.delete(
    "/users/delete-account",
    responses={
        200: {"description": "User successfully deleted"},
        401: {"description": "Invalid password"},
        404: {"description": "User not found"}
    }
)
async def remove_user(
        password: str,
        db: AsyncSession = Depends(get_db),
        token: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Delete user account.

    Requires authentication and password verification.
    """
    try:
        # Get user email from token
        payload = verify_jwt_token(token)
        email = payload.get("sub")
        
        await delete_user(db, email, password)
        logger.info("User deleted", event_type="user_deleted", email=email)
        return {"message": "User deleted successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        # Get user email from token for logging
        try:
            payload = verify_jwt_token(token)
            email = payload.get("sub")
            logger.error("User deletion failed", event_type="user_deletion_error", email=email, error_type=type(e).__name__)
        except:
            logger.error("User deletion failed", event_type="user_deletion_error", error_type=type(e).__name__)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        ) from e
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions without changing status code
        logger.error(f"HTTP exception in remove_user: {http_ex.status_code}: {http_ex.detail}",
                    event_type="user_deletion_error",
                    error_type="HTTPException",
                    error_details=str(http_ex.detail))
        raise http_ex
    except Exception as e:
        logger.error(f"Unhandled exception in remove_user: {type(e).__name__}: {str(e)}",
                    event_type="debug_user_deletion_error",
                    error_type=type(e).__name__,
                    error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting user: {str(e)}"
        ) from e


@router.post(
    "/logout",
    responses={
        200: {"description": "Successfully logged out"},
        401: {"description": "Invalid or expired token"}
    }
)
async def logout(token: str = Depends(oauth2_scheme)) -> Dict[str, str]:
    """
    Logout endpoint that validates the JWT token.
    
    Note: In a JWT-based system, the token remains valid until expiration.
    The client should handle token removal from their storage.
    """
    try:
        # Verify token and get payload
        payload = verify_jwt_token(token)
        subject = payload.get("sub")
        
        logger.info("User logged out", event_type="user_logout", email=subject)
        
        return {"message": "Successfully logged out"}
    except jwt.JWTError as e:
        logger.error("Logout failed - invalid token", event_type="logout_error", error_type="jwt_error", error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
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
        reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?token={token}"

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
    except (UserNotFoundError, ValueError, jwt.JWTError) as e:
        logger.error("Password reset request failed", event_type="password_reset_request_error", email=request.email, error=str(e))
        # Return same message to prevent email enumeration
        return {"message": "Password reset link sent to email if account exists"}


@router.post(
    "/reset-password",
    responses={
        200: {"description": "Password successfully reset"},
        400: {"description": "Invalid or expired reset token"}
    }
)
async def reset_password_with_token(
    reset_data: PasswordReset,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Reset password using the token received via email."""
    try:
        user_id = await verify_reset_token(reset_data.token)
        await reset_password(db, user_id, reset_data.new_password)

        # Send confirmation email
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            user_service = UserService(db)
            await user_service.send_password_change_confirmation(user, background_tasks)

        logger.info("Password reset successful", event_type="password_reset_success", user_id=user_id)
        return {"message": "Password has been reset successfully"}
    except (UserNotFoundError, jwt.JWTError, ValueError) as e:
        logger.error("Password reset failed", event_type="password_reset_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        ) from e


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
    """Refresh an existing JWT token."""
    try:
        # Verify the existing token
        payload = verify_jwt_token(refresh_request.token)
        
        # Get email from token
        email = payload.get("sub")
        
        # Get user by email
        user = await get_user_by_email(db, email)
            
        if not user:
            logger.error("Token refresh failed - user not found", event_type="token_refresh_error", email=email, error_type="user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Calculate new expiration time
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Create new access token - always use email as subject for new tokens
        access_token = create_access_token(
            data={
                "sub": user.email,  # Always use email for new tokens
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info("Token refreshed successfully", event_type="token_refresh_success", email=user.email)

        return Token(access_token=access_token, token_type="bearer")

    except jwt.JWTError as e:
        logger.error("Token refresh failed - invalid token", event_type="token_refresh_error", error_type="jwt_error", error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        ) from e


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        200: {
            "description": "User profile retrieved successfully"
        },
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"}
    }
)
async def get_current_user_profile(
    user_id: int | None = None,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """
    Retrieve the profile of the authenticated user.
    For non-admin users, any provided user_id is ignored.
    Admin users can retrieve other users' profiles by providing a valid user_id.
    """
    try:
        # Verify token and get payload
        payload = verify_jwt_token(token)
        
        # Use provided user_id or get from token
        target_user_id = user_id if user_id is not None else payload.get("id")
        
        # Get email from token
        email = payload.get("sub")
        
        # Get user by email
        user = await get_user_by_email(db, email)
            
        if not user:
            logger.error("User not found", event_type="user_lookup_error", email=email)
            raise UserNotFoundError("User not found")
            
        # If requesting another user's profile, verify admin status
        if user_id is not None and user_id != user.id:
            if not payload.get("is_admin", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view other users' profiles"
                )
            # Get user by ID for admin lookup
            result = await db.execute(select(User).where(User.id == user_id))
            target_user = result.scalar_one_or_none()
            
            if not target_user:
                logger.error(
                    "Admin lookup failed - user not found",
                    event_type="profile_retrieval_error",
                    user_id=user_id,
                    admin_email=user.email
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {user_id} not found"
                )
            
            # Update user reference to target user for response
            user = target_user
        
        logger.info("User profile retrieved", event_type="profile_retrieved", email=user.email)
        
        return UserResponse(
            email=user.email,
            is_verified=user.is_verified
        )
        
    except jwt.JWTError as e:
        logger.error("Profile retrieval failed - token error", event_type="profile_retrieval_error", error_type="JWTError", error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        ) from e
    except UserNotFoundError as e:
        logger.error("Profile retrieval failed - user not found", event_type="profile_retrieval_error", error_type="UserNotFoundError", error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from e


@router.get("/users/{user_id}/email",
    response_model=Dict[str, str],
    responses={
        200: {"description": "User email retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_email_by_user_id(user_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Get user's email by user ID without requiring authentication."""
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(
                "Email retrieval failed - user not found",
                event_type="email_retrieval_error",
                user_id=user_id,
                error_type="user_not_found"
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        logger.info(
            "Email retrieved by user_id",
            event_type="email_retrieved",
            user_id=user_id
        )
        return {"email": str(user.email)}
    except HTTPException as http_ex:
        # Re-log but keep the original HTTPException status code
        logger.error(
            "Failed to retrieve email by user_id",
            event_type="email_retrieval_error",
            user_id=user_id,
            error_type="HTTPException",
            error_details=str(http_ex.detail)
        )
        # Re-raise the same HTTPException to maintain the status code
        raise http_ex
    except Exception as e:
        logger.error(
            "Failed to retrieve email by user_id",
            event_type="email_retrieval_error",
            user_id=user_id,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                           detail="Internal server error when retrieving user email")

@router.post(
    "/test-email",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Test email sent successfully"},
        500: {"description": "Failed to send test email"}
    }
)
async def test_email(
    email_test: Dict[str, str],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Test endpoint to verify email sending functionality.
    Requires an email address to send the test to.
    
    Example request:
    ```json
    {
        "email": "test@example.com"
    }
    ```
    """
    try:
        email = email_test.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email address is required"
            )
            
        # Create email service
        email_service = EmailService(background_tasks, db)
        
        # Send a test email directly (not in background)
        from app.core.email import send_email
        result = await send_email(
            subject="Test Email from Auth Service",
            recipients=[email],
            body="<p>This is a test email to verify the email sending functionality.</p>"
        )
        
        logger.info(
            "Test email sent",
            event_type="test_email_sent",
            recipient=email,
            status_code=result
        )
        
        return {
            "message": "Test email sent",
            "status_code": result,
            "recipient": email
        }
    except Exception as e:
        logger.error(
            "Failed to send test email",
            event_type="test_email_error",
            error=str(e),
            error_type=type(e).__name__
        )
        
        return {
            "message": "Failed to send test email",
            "error": str(e),
            "error_type": type(e).__name__
        }


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


# Google OAuth Endpoints

@router.get(
    "/oauth/google/login",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Google login URL generated"},
        500: {"description": "Failed to generate login URL"}
    }
)
async def google_login(
    redirect_uri: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Generate Google OAuth login URL.
    
    Args:
        redirect_uri: Optional custom redirect URI
        db: Database session
        
    Returns:
        Dict with login URL
    """
    try:
        oauth_service = GoogleOAuthService(db)
        auth_url = await oauth_service.get_authorization_url(redirect_uri)
        
        logger.info(
            "Generated Google OAuth URL",
            event_type="oauth_url_generated",
            redirect_uri=redirect_uri or settings.GOOGLE_REDIRECT_URI
        )
        
        return {"auth_url": auth_url}
    
    except Exception as e:
        logger.error(
            "Failed to generate Google OAuth URL",
            event_type="oauth_url_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating Google login URL: {str(e)}"
        )

@router.post(
    "/oauth/google/callback",
    response_model=Token,
    responses={
        200: {"description": "Successfully authenticated with Google"},
        400: {"description": "Invalid OAuth callback"}
    }
)
async def google_callback(
    callback: GoogleAuthCallback,
    db: AsyncSession = Depends(get_db)
) -> Token:
    """
    Process Google OAuth callback and generate JWT token.
    
    Args:
        callback: Callback data with authorization code
        db: Database session
        
    Returns:
        JWT token same as regular login
    """
    try:
        oauth_service = GoogleOAuthService(db)
        user, access_token = await oauth_service.login_with_google(callback.code)
        
        logger.info(
            "Google OAuth login successful",
            event_type="oauth_login_success",
            user_id=user.id,
            email=user.email
        )
        
        return Token(access_token=access_token, token_type="bearer")
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(
            "Google OAuth callback error",
            event_type="oauth_callback_error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error processing Google callback: {str(e)}"
        )

@router.post(
    "/link/google",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Google account linked successfully"},
        401: {"description": "Not authenticated or invalid password"},
        400: {"description": "Invalid OAuth callback"}
    }
)
async def link_google_account(
    link_request: AccountLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Link Google account to existing user.
    
    Args:
        link_request: Link request with Google auth code and password
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success message
    """
    try:
        # Verify password
        if not verify_password(link_request.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid password"
            )
            
        oauth_service = GoogleOAuthService(db)
        
        # Exchange code for tokens
        tokens = await oauth_service.exchange_code_for_tokens(link_request.code)
        
        # Get user profile
        profile = await oauth_service.get_user_profile(tokens['access_token'])
        
        # Link account
        await oauth_service.link_google_account(current_user, profile)
        
        return {"message": "Google account linked successfully"}
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(
            "Google account linking error",
            event_type="oauth_link_error",
            user_id=current_user.id,
            email=current_user.email,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error linking Google account: {str(e)}"
        )

@router.post(
    "/unlink/google",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Google account unlinked successfully"},
        400: {"description": "Cannot unlink account without password"},
        401: {"description": "Not authenticated"}
    }
)
async def unlink_google_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Unlink Google account from user.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Success message
    """
    try:
        oauth_service = GoogleOAuthService(db)
        await oauth_service.unlink_google_account(current_user)
        
        return {"message": "Google account unlinked successfully"}
        
    except HTTPException as http_ex:
        # Re-raise HTTP exceptions
        raise http_ex
    except Exception as e:
        logger.error(
            "Google account unlinking error",
            event_type="oauth_unlink_error",
            user_id=current_user.id,
            email=current_user.email,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error unlinking Google account: {str(e)}"
        )
