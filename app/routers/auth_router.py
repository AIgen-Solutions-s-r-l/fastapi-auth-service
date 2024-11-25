from datetime import timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging_config import LogConfig
from app.core.exceptions import UserAlreadyExistsError, UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token
from app.schemas.auth_schemas import LoginRequest, Token, UserCreate, PasswordChange
from app.services.user_service import (
    create_user, authenticate_user, get_user_by_username,
    update_user_password, delete_user
)

router = APIRouter(tags=["authentication"])
logger = LogConfig.get_logger()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@router.post("/login", response_model=Token)
async def login(
        credentials: LoginRequest,
        db: AsyncSession = Depends(get_db)
) -> Token:
    try:
        user = await authenticate_user(db, credentials.username, credentials.password)
        if not user:
            logger.warning("Authentication failed", extra={
                "event_type": "login_failed",
                "username": credentials.username,
                "reason": "invalid_credentials"
            })
            raise InvalidCredentialsError()

        access_token = create_access_token(
            data={"sub": user.username},
            expires_delta=timedelta(minutes=60)
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
        user: UserCreate,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    try:
        new_user = await create_user(db, user.username, str(user.email), user.password)
        access_token = create_access_token(
            data={"sub": new_user.username},
            expires_delta=timedelta(minutes=60)
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
    except Exception as e:
        logger.error("Registration error", extra={
            "event_type": "registration_error",
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        raise


@router.get("/users/{username}")
async def get_user_details(
        username: str,
        db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
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


@router.put("/users/{username}/password")
async def change_password(
        username: str,
        passwords: PasswordChange,
        db: AsyncSession = Depends(get_db),
        _: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
    try:
        await update_user_password(db, username, passwords.current_password, passwords.new_password)
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.delete("/users/{username}")
async def remove_user(
        username: str,
        password: str,
        db: AsyncSession = Depends(get_db),
        _: str = Depends(oauth2_scheme)
) -> Dict[str, str]:
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout")
async def logout() -> Dict[str, str]:
    return {"message": "Successfully logged out"}