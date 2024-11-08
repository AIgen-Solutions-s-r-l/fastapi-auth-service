from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.user_service import create_user
from app.core.security import create_access_token
from pydantic import BaseModel
from datetime import timedelta
import  logging

router = APIRouter()
logger = logging.getLogger(__name__)

class UserCreate(BaseModel):
    """
    Pydantic model for creating a new user.
    """
    username: str
    email: str
    password: str

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
    logger.info(f"Database Data: {db.bind.url}")
    try:
        new_user = await create_user(db, user.username, user.email, user.password)
        return {"message": "User registered successfully", "user": new_user.username}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
