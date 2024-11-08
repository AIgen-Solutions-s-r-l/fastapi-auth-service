# app/routers/auth_router.py
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.services.user_service import create_user, authenticate_user

router = APIRouter()
logger = logging.getLogger(__name__)

class UserCreate(BaseModel):
    """
    Pydantic model for creating a new user.
    """
    username: str
    email: str
    password: str


class Token(BaseModel):
    """
    Pydantic model for token response.
    """
    access_token: str
    token_type: str


@router.post("/login", response_model=Token)
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(),
        db: AsyncSession = Depends(get_db)
):
    """
    Authenticate a user and return a JWT token.

    Args:
        form_data (OAuth2PasswordRequestForm): The login credentials.
        db (AsyncSession): The database session.

    Returns:
        Token: An object containing the access token and token type.

    Raises:
        HTTPException: If authentication fails due to invalid credentials.
    """
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with 30 minutes expiration
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=30)
    )

    logger.info(f"User {user.username} successfully logged in")
    return Token(access_token=access_token, token_type="bearer")

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Registers a new user by creating a record in the database.

    Args:
        user (UserCreate): The user creation details.
        db (AsyncSession): The database session.

    Returns:
        dict: A message indicating the user was successfully registered.

    Raises:
        HTTPException: If the username already exists in the database.
    """
    try:
        new_user = await create_user(db, user.username, user.email, user.password)
        return {"message": "User registered successfully", "user": new_user.username}
    except ValueError as e:
        logger.error(f"Validation Error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
