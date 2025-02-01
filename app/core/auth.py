from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError, UserNotFoundError
from app.core.security import verify_jwt_token
from app.models.user import User
from app.services.user_service import get_user_by_username

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db)
):
    try:
        payload = verify_jwt_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise InvalidCredentialsError()
    except JWTError:
        raise InvalidCredentialsError()

    user = await get_user_by_username(db, username)
    if user is None:
        raise UserNotFoundError(username)
    return user
