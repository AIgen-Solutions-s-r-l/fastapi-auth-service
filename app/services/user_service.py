"""Service layer for user-related operations."""

from datetime import datetime, UTC, timedelta
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import get_password_hash, verify_password
from app.models.user import User


class UserService:
    """Service class for user operations."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username to look up

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: Email to look up

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        is_admin: bool = False
    ) -> User:
        """
        Create a new user.

        Args:
            username: Username for new user
            email: Email for new user
            password: Plain text password
            is_admin: Whether user is admin

        Returns:
            User: Created user

        Raises:
            HTTPException: If username/email already exists
        """
        try:
            user = User(
                username=username,
                email=email,
                hashed_password=get_password_hash(password),
                is_admin=is_admin
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username or email already registered"
            )

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user.

        Args:
            username: Username to authenticate
            password: Plain text password to verify

        Returns:
            Optional[User]: Authenticated user if successful, None otherwise
        """
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def update_user_email(self, username: str, current_password: str, new_email: str) -> User:
        """
        Update user's email address.

        Args:
            username: Username of user to update
            current_password: Current password for verification
            new_email: New email address

        Returns:
            User: Updated user object

        Raises:
            HTTPException: If authentication fails or email is already in use
        """
        user = await self.authenticate_user(username, current_password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        # Check if new email is already in use
        existing_user = await self.get_user_by_email(new_email)
        if existing_user and existing_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        try:
            user.email = new_email
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    async def delete_user(self, username: str, password: str) -> bool:
        """
        Delete a user.

        Args:
            username: Username of user to delete
            password: Password for verification

        Returns:
            bool: True if user was deleted, False otherwise

        Raises:
            HTTPException: If user not found or password incorrect
        """
        user = await self.authenticate_user(username, password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        try:
            await self.db.delete(user)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error deleting user: {str(e)}"
            )


# Function exports for backward compatibility
async def create_user(db: AsyncSession, username: str, email: str, password: str, is_admin: bool = False) -> User:
    """Create a new user."""
    service = UserService(db)
    return await service.create_user(username, email, password, is_admin)

async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    """Authenticate a user."""
    service = UserService(db)
    return await service.authenticate_user(username, password)

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Get user by username."""
    service = UserService(db)
    return await service.get_user_by_username(username)

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email."""
    service = UserService(db)
    return await service.get_user_by_email(email)

async def delete_user(db: AsyncSession, username: str, password: str) -> bool:
    """Delete a user."""
    service = UserService(db)
    return await service.delete_user(username, password)

async def update_user_password(db: AsyncSession, username: str, current_password: str, new_password: str) -> bool:
    """Update user password."""
    service = UserService(db)
    user = await service.authenticate_user(username, current_password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    user.hashed_password = get_password_hash(new_password)
    await db.commit()
    return True

async def create_password_reset_token(db: AsyncSession, email: str) -> str:
    """Create a password reset token."""
    service = UserService(db)
    user = await service.get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    # TODO: Implement token creation
    return "dummy_token"

async def verify_reset_token(token: str) -> int:
    """Verify a password reset token."""
    # TODO: Implement token verification
    return 1

async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> bool:
    """Reset user password."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    user.hashed_password = get_password_hash(new_password)
    await db.commit()
    return True
