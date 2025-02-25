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
    PasswordResetRequest, PasswordReset, RefreshToken, EmailChange
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
    response_model=Dict[str, Any],
    responses={
        201: {
            "description": "User successfully registered",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User registered successfully",
                        "username": "john_doe",
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer"
                    }
                }
            }
        },
        409: {"description": "Username or email already exists"}
    }
)
async def register_user(
        user: UserCreate,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Register a new user and return access token for immediate authentication.

    Returns:
        Dict containing:
        - success message
        - username
        - JWT access token
        - token type (always "bearer")
    """
    try:
        new_user = await create_user(db, user.username, str(user.email), user.password)

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": new_user.id,
                "is_admin": new_user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info("User registered", event_type="user_registered", username=new_user.username, email=str(user.email))

        return {
            "message": "User registered successfully",
            "username": new_user.username,
            "access_token": access_token,
            "token_type": "bearer"
        }
    except UserAlreadyExistsError as e:
        logger.error("Registration failed", event_type="registration_error", username=user.username, email=str(user.email), error_type="user_exists")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.get(
    "/users/{username}",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "User details retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        username: str,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Retrieve user details by username."""
    try:
        user = await get_user_by_username(db, username)
        logger.info("User details retrieved", event_type="user_details_retrieved", username=username)
        # Add debug logging to check if user is None
        logger.info(f"User object is: {user}", event_type="user_details_debug")
        if user is None:
            logger.error("User object is None", event_type="user_lookup_error", username=username)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return {
            "username": user.username,
            "email": str(user.email)
        }
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
                        "email": "new.email@example.com"
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
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> Dict[str, Any]:
    """
    Change user's email address.

    Requires authentication and current password verification.
    The new email must not be already registered by another user.

    Args:
        username: Username of the user
        email_change: New email and current password
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
        service = UserService(db)
        updated_user = await service.update_user_email(
            username,
            email_change.current_password,
            str(email_change.new_email)
        )

        logger.info(
            "Email changed successfully",
            event_type="email_changed",
            username=username,
            new_email=str(email_change.new_email)
        )

        return {
            "message": "Email updated successfully",
            "username": updated_user.username,
            "email": str(updated_user.email)
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
        db: AsyncSession = Depends(get_db),
        _: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Change user password.

    Requires authentication and verification of current password.
    """
    try:
        await update_user_password(
            db,
            username,
            passwords.current_password,
            passwords.new_password
        )
        logger.info("Password changed", event_type="password_changed", username=username)
        return {"message": "Password updated successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("Password change failed", event_type="password_change_error", username=username, error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
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


@router.post("/password-reset-request")
async def request_password_reset(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Request a password reset link to be sent via email."""
    try:
        token = await create_password_reset_token(db, request.email)
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"

        background_tasks.add_task(
            send_email,
            to_email=request.email,
            subject="Password Reset Request",
            template="password_reset.html",
            context={
                "reset_link": reset_link,
                "username": request.email
            }
        )

        return {"message": "Password reset link sent to email if account exists"}
    except (UserNotFoundError, ValueError, jwt.JWTError) as e:
        logger.error("Password reset request failed", event_type="password_reset_request_error", email=request.email, error=str(e))
        # Return same message to prevent email enumeration
        return {"message": "Password reset link sent to email if account exists"}


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
    response_model=Dict[str, Any],
    responses={
        200: {
            "description": "User profile retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "username": "john_doe",
                        "email": "john@example.com"
                    }
                }
            }
        },
        401: {"description": "Not authenticated"},
        404: {"description": "User not found"}
    }
)
async def get_current_user_profile(
    user_id: int | None = None,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
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
        
        return {
            "username": user.username,
            "email": str(user.email)
        }
        
    except (jwt.JWTError, UserNotFoundError) as e:
        logger.error("Profile retrieval failed", event_type="profile_retrieval_error", error_type=type(e).__name__, error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        ) from e


@router.post("/reset-password")
async def reset_password_with_token(
    reset_data: PasswordReset,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Reset password using the token received via email."""
    try:
        user_id = await verify_reset_token(reset_data.token)
        await reset_password(db, user_id, reset_data.new_password)

        logger.info("Password reset successful", event_type="password_reset_success", user_id=user_id)
        return {"message": "Password has been reset successfully"}
    except (UserNotFoundError, jwt.JWTError, ValueError) as e:
        logger.error("Password reset failed", event_type="password_reset_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        ) from e


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
        return {"email": str(user.email), "username": user.username}
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
