from datetime import timedelta, datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token
from app.schemas.auth_schemas import LoginRequest, Token, UserCreate, PasswordChange
from app.services.user_service import (
    create_user, authenticate_user, get_user_by_username,
    update_user_password, delete_user
)
from app.core.logging_config import LogConfig

router = APIRouter(tags=["authentication"])
logger = LogConfig.get_logger()
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
            logger.warning("Authentication failed", extra={
                "event_type": "login_failed",
                "username": credentials.username,
                "reason": "invalid_credentials"
            })
            raise InvalidCredentialsError()

        # Calculate expiration time
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.utcnow() + expires_delta
        
        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", extra={
            "event_type": "login_success",
            "username": user.username
        })
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error("Login error", extra={
            "event_type": "login_error",
            "username": credentials.username,
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        raise InvalidCredentialsError()

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
        
        # Calculate expiration time
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.utcnow() + expires_delta
        
        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": new_user.id,
                "is_admin": new_user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info("User registered", extra={
            "event_type": "user_registered",
            "username": new_user.username,
            "email": str(user.email)
        })

        return {
            "message": "User registered successfully",
            "username": new_user.username,
            "access_token": access_token,
            "token_type": "bearer"
        }
    except UserAlreadyExistsError as e:
        logger.error("Registration failed", extra={
            "event_type": "registration_error",
            "username": user.username,
            "email": str(user.email),
            "error_type": "user_exists"
        })
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

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
        logger.info("User details retrieved", extra={
            "event_type": "user_details_retrieved",
            "username": username
        })
        return user
    except UserNotFoundError as e:
        logger.error("User lookup failed", extra={
            "event_type": "user_lookup_error",
            "username": username,
            "error_type": "user_not_found"
        })
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

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
        logger.info("Password changed", extra={
            "event_type": "password_changed",
            "username": username
        })
        return {"message": "Password updated successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("Password change failed", extra={
            "event_type": "password_change_error",
            "username": username,
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

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
        logger.info("User deleted", extra={
            "event_type": "user_deleted",
            "username": username
        })
        return {"message": "User deleted successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.error("User deletion failed", extra={
            "event_type": "user_deletion_error",
            "username": username,
            "error_type": type(e).__name__
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

@router.post("/logout")
async def logout() -> Dict[str, str]:
    """
    Logout endpoint for client-side cleanup.

    Note: In a JWT-based system, the token remains valid until expiration.
    The client should handle token removal from their storage.
    """
    return {"message": "Successfully logged out"}