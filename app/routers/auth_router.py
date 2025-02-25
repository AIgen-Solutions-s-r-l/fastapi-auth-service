"""Router module for authentication-related endpoints including login, registration, and password management."""

from datetime import timedelta, datetime, timezone
from typing import Dict, Any
from jose import jwt, JWTError
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token, verify_jwt_token
from app.schemas.auth_schemas import (
    LoginRequest, Token, UserCreate, PasswordChange,
    PasswordResetRequest, PasswordReset, RefreshToken, EmailChange,
    VerifyEmail, ResendVerification, UserResponse, RegistrationResponse
)
from app.services.user_service import (
    create_user, authenticate_user, get_user_by_username,
    update_user_password, delete_user, create_password_reset_token,
    verify_reset_token, reset_password, get_user_by_email, UserService
)
from app.models.user import User
from app.log.logging import logger
from app.core.email import send_email
from app.core.config import settings
from app.services.email_service import EmailService


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
        user = await authenticate_user(db, credentials.username, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", username=credentials.username, reason="invalid_credentials")
            raise InvalidCredentialsError()

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", username=user.username)
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error("Login error", event_type="login_error", username=credentials.username, error_type=type(e).__name__, error_details=str(e))
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
                        "username": "john_doe",
                        "email": "john@example.com",
                        "verification_sent": True
                    }
                }
            }
        },
        409: {"description": "Username or email already exists"}
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
        - username
        - email
        - verification_sent status
    """
    try:
        # Create the user (initially not verified)
        new_user = await create_user(db, user.username, str(user.email), user.password)
        
        # Send verification email
        user_service = UserService(db)
        verification_sent = await user_service.send_verification_email(new_user, background_tasks)

        logger.info("User registered", 
                  event_type="user_registered", 
                  username=new_user.username, 
                  email=str(user.email),
                  verification_sent=verification_sent)

        return RegistrationResponse(
            message="User registered successfully. Please check your email to verify your account.",
            username=new_user.username,
            email=str(new_user.email),
            verification_sent=verification_sent
        )
        
    except UserAlreadyExistsError as e:
        logger.error("Registration failed", 
                   event_type="registration_error", 
                   username=user.username, 
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
            username=user.username
        )
        
        # Generate a token for immediate login
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta
        
        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        
        return {
            "message": "Email verified successfully",
            "username": user.username,
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
            username=user.username,
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
    "/users/{username}",
    response_model=UserResponse,
    responses={
        200: {"description": "User details retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        username: str,
        db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Retrieve user details by username."""
    try:
        user = await get_user_by_username(db, username)
        logger.info("User details retrieved", event_type="user_details_retrieved", username=username)
        if user is None:
            logger.error("User object is None", event_type="user_lookup_error", username=username)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        return UserResponse(
            username=user.username,
            email=user.email,
            is_verified=user.is_verified
        )
        
    except UserNotFoundError as e:
        logger.error("User lookup failed", event_type="user_lookup_error", username=username, error_type="user_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.put(
    "/users/{username}/email",
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "Email successfully updated",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Email updated successfully",
                        "username": "john_doe",
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
    username: str,
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
        username: Username of the user
        email_change: New email and current password
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
        if payload.get("sub") != username and not payload.get("is_admin", False):
            logger.error(
                "Unauthorized email change attempt",
                event_type="email_change_error",
                username=username,
                attempted_by=payload.get("sub"),
                error_type="unauthorized"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to change other users' email"
            )

        # Update email through service
        user_service = UserService(db)
        updated_user = await user_service.update_user_email(
            username,
            email_change.current_password,
            str(email_change.new_email)
        )

        # Send verification email for new email address
        verification_sent = await user_service.send_verification_email(updated_user, background_tasks)

        logger.info(
            "Email changed successfully",
            event_type="email_changed",
            username=username,
            new_email=str(email_change.new_email),
            verification_sent=verification_sent
        )

        return {
            "message": "Email updated successfully. Please verify your new email address.",
            "username": updated_user.username,
            "email": str(updated_user.email),
            "verification_sent": verification_sent
        }

    except JWTError as e:
        # Handle JWT authentication errors
        logger.error(
            "Email change failed - invalid token",
            event_type="email_change_error",
            username=username,
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
            username=username,
            error_type=type(e).__name__,
            error_details=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating email"
        ) from e

@router.put(
    "/users/{username}/password",
    responses={
        200: {"description": "Password successfully updated"},
        401: {"description": "Invalid current password"},
        404: {"description": "User not found"}
    }
)
async def change_password(
        username: str,
        passwords: PasswordChange,
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
        _: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Change user password and send confirmation email.

    Requires authentication and verification of current password.
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
            username,
            passwords.current_password,
            passwords.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
            
        # Get user for email
        user = await user_service.get_user_by_username(username)
        if user:
            # Send confirmation email
            await user_service.send_password_change_confirmation(user, background_tasks)
        
        logger.info("Password changed", event_type="password_changed", username=username)
        return {"message": "Password updated successfully"}
        
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("Password change failed", event_type="password_change_error", username=username, error_type=type(e).__name__)
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
    "/users/{username}",
    responses={
        200: {"description": "User successfully deleted"},
        401: {"description": "Invalid password"},
        404: {"description": "User not found"}
    }
)
async def remove_user(
        username: str,
        password: str,
        db: AsyncSession = Depends(get_db),
        _: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Delete user account.

    Requires authentication and password verification.
    """
    try:
        await delete_user(db, username, password)
        logger.info("User deleted", event_type="user_deleted", username=username)
        return {"message": "User deleted successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("User deletion failed", event_type="user_deletion_error", username=username, error_type=type(e).__name__)
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
        username = payload.get("sub")
        
        logger.info("User logged out", event_type="user_logout", username=username)
        
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
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        # Create email service
        email_service = EmailService(background_tasks, db)
        
        # Get user for email
        user_service = UserService(db)
        user = await user_service.get_user_by_email(str(request.email))
        
        if user:
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
        
        # Get user from database to ensure they still exist
        user = await get_user_by_username(db, payload.get("sub"))
        if not user:
            logger.error("Token refresh failed - user not found", event_type="token_refresh_error", username=payload.get("sub"), error_type="user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Calculate new expiration time
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Create new access token
        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info("Token refreshed successfully", event_type="token_refresh_success", username=user.username)

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
        
        # Get user from database
        user = await get_user_by_username(db, payload.get("sub"))
        if not user:
            raise UserNotFoundError("User not found")
            
        # If requesting another user's profile, verify admin status
        if user_id is not None and user_id != user.id:
            if not payload.get("is_admin", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view other users' profiles"
                )
            user = await get_user_by_username(db, str(user_id))
            if not user:
                raise UserNotFoundError("Requested user not found")
        
        logger.info("User profile retrieved", event_type="profile_retrieved", username=user.username)
        
        return UserResponse(
            username=user.username,
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


@router.get("/users/{user_id}/profile",
    response_model=Dict[str, str],
    responses={
        200: {"description": "User email and username retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_email_and_username_by_user_id(user_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Get user's email and username by user ID without requiring authentication."""
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            # Make sure we call the warning logger correctly
            logger.warning(
                "Profile retrieval failed - user not found",
                event_type="profile_retrieval_error",
                user_id=user_id,
                error_type="user_not_found"
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        logger.info(
            "Email and username retrieved by user_id",
            event_type="profile_retrieved",
            user_id=user_id
        )
        return {
            "email": str(user.email), 
            "username": user.username,
            "is_verified": user.is_verified
        }
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
                           detail="Internal server error when retrieving user profile")
