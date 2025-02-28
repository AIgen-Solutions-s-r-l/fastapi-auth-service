"""Authentication utilities."""

from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthException
from app.models.user import User
from app.services.user_service import UserService

from app.core.config import settings
from app.core.security import create_access_token, verify_jwt_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.
    Supports both email and username in the 'sub' claim for backward compatibility.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        AuthException: If token is invalid or user not found
    """
    credentials_exception = AuthException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_jwt_token(token)
        subject: str = payload.get("sub")
        if subject is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_service = UserService(db)
    
    # Try to find user by email first (new tokens)
    user = await user_service.get_user_by_email(subject)
    
    # If not found, try to find by username (old tokens)
    if user is None:
        user = await user_service.get_user_by_username(subject)
        
    if user is None:
        raise credentials_exception
        
    return user
