from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError, UserNotFoundError
from app.core.security import verify_jwt_token
from app.models.user import User
from app.services.user_service import get_user_by_username

logger = logging.getLogger("auth")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    '''
    Retrieve the current authenticated user via JWT token.
    
    Args:
        token (str): JWT token.
        db (AsyncSession): Database session.
    
    Returns:
        User: The authenticated user instance.
    
    Raises:
        InvalidCredentialsError: If JWT verification fails.
        UserNotFoundError: If no user is found.
    '''
    try:
        payload = verify_jwt_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise InvalidCredentialsError()
    except JWTError as e:
        logger.error("JWT verification failed: %s", e)
        raise InvalidCredentialsError() from e

    user = await get_user_by_username(db, username)
    if user is None:
        raise UserNotFoundError(username)
    return user
