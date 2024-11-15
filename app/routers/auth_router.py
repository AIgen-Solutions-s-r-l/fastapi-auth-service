# app/routers/auth_router.py
import logging
from datetime import timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
    InvalidCredentialsError
)
from app.core.security import create_access_token
from app.services.user_service import (
    create_user,
    authenticate_user,
    get_user_by_username,
    update_user_password,
    delete_user
)

router = APIRouter(tags=["authentication"])
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


class UserCreate(BaseModel):
    """Pydantic model for creating a new user."""
    username: str
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "strongpassword123"
            }
        }


class Token(BaseModel):
    """Pydantic model for token response."""
    access_token: str
    token_type: str


class PasswordChange(BaseModel):
    """Pydantic model for password change request."""
    current_password: str
    new_password: str

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "oldpassword123",
                "new_password": "newpassword123"
            }
        }


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
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        user = await authenticate_user(db, form_data.username, form_data.password)
        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=30)
        )
        logger.info(f"User {user.username} successfully logged in")
        return Token(access_token=access_token, token_type="bearer")
    except (UserNotFoundError, InvalidCredentialsError) as e:
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=Dict[str, str],
    responses={
        201: {"description": "User successfully registered"},
        409: {"description": "Username or email already exists"}
    }
)
async def register_user(
        user: UserCreate,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """Register a new user."""
    try:
        new_user = await create_user(db, user.username, user.email, user.password)
        logger.info(f"New user registered: {new_user.username}")
        return {"message": "User registered successfully", "username": new_user.username}
    except UserAlreadyExistsError as e:
        logger.error(f"Registration failed: {str(e)}")
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
        return user
    except UserNotFoundError as e:
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
        token: str = Depends(oauth2_scheme)
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
        logger.info(f"Password changed for user: {username}")
        return {"message": "Password updated successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
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
        token: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    """
    Delete user account.

    Requires authentication and password verification.
    """
    try:
        await delete_user(db, username, password)
        logger.info(f"User deleted: {username}")
        return {"message": "User deleted successfully"}
    except (UserNotFoundError, InvalidCredentialsError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


# Opzionale: endpoint per logout (invalidare il token)
@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme)) -> Dict[str, str]:
    """
    Logout user.

    Note: In a JWT-based system, the token remains valid until expiration.
    This endpoint is more for client-side cleanup.
    """
    return {"message": "Successfully logged out"}
