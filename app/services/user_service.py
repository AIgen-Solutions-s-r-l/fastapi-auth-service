"""Service module for user-related operations including authentication, registration, and password management."""

# app/services/user_service.py
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from jose import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError, UserAlreadyExistsError, DatabaseOperationError
from app.core.security import verify_password, get_password_hash
from app.models.user import User, PasswordResetToken
from app.core.email import send_email
from app.core.config import settings


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    """
    Authenticate a user by verifying their username and password.

    Args:
        db (AsyncSession): The database session.
        username (str): The username to authenticate.
        password (str): The password to verify.

    Returns:
        User | None: The authenticated user if successful, None otherwise.
    """
    result = await db.execute(select(User).filter(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user


async def create_user(db: AsyncSession, username: str, email: str, password: str) -> User:
    """Creates a new user and saves it to the database."""
    # Verify username
    result = await db.execute(select(User).filter(User.username == username))
    if result.scalar_one_or_none():
        raise UserAlreadyExistsError(f"username: {username}")

    # Verify email
    result = await db.execute(select(User).filter(User.email == email))
    if result.scalar_one_or_none():
        raise UserAlreadyExistsError(f"email: {email}")

    try:
        hashed_password = get_password_hash(password)
        new_user = User(username=username, email=email, hashed_password=hashed_password)
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user
    except Exception as e:
        await db.rollback()
        raise DatabaseOperationError(f"Error creating user: {str(e)}") from e


async def get_user_by_username(db: AsyncSession, username: str) -> Dict[str, Any]:
    """Retrieve a user by username using a raw SQL query and return the user data as JSON."""
    try:
        query = text("SELECT id, username, email FROM users WHERE username = :username")
        result = await db.execute(query, {"username": username})
        user = result.first()

        if not user:
            raise UserNotFoundError(f"username: {username}")

        # Convert to dict using dict(zip()) instead of _mapping
        user_dict = dict(zip(['id', 'username', 'email'], user))
        return jsonable_encoder(user_dict)

    except UserNotFoundError:
        raise
    except Exception as e:
        raise DatabaseOperationError(f"Error retrieving user: {str(e)}") from e


async def update_user_password(
        db: AsyncSession,
        username: str,
        current_password: str,
        new_password: str
) -> User:
    """Update a user's password after verifying their current password."""
    user = await authenticate_user(db, username, current_password)

    try:
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as e:
        await db.rollback()
        raise DatabaseOperationError(f"Error updating password: {str(e)}") from e


async def delete_user(db: AsyncSession, username: str, password: str) -> None:
    """Delete a user after verifying their password."""
    user = await authenticate_user(db, username, password)

    try:
        await db.delete(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise DatabaseOperationError(f"Error deleting user: {str(e)}") from e


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Generate reset token and send reset email to user."""
    # Find user by email
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        return  # Silent return if user doesn't exist
    
    # Generate secure token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)
    
    # Store token in database
    reset_token = PasswordResetToken(
        token=token,
        user_id=user.id,
        expires_at=expires_at
    )
    db.add(reset_token)
    await db.commit()
    
    # Create reset link
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    
    # Send email
    await send_email(
        to_email=email,
        subject="Password Reset Request",
        template="password_reset.html",
        context={
            "username": user.username,
            "reset_link": reset_link,
            "expires_in": "24 hours"
        }
    )


async def reset_password_with_token(
    db: AsyncSession,
    token: str,
    new_password: str
) -> None:
    """Reset user password using valid reset token."""
    # Find valid token
    query = select(PasswordResetToken).where(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False,  # Not already used
        PasswordResetToken.expires_at > datetime.utcnow()  # Not expired
    )
    result = await db.execute(query)
    reset_token = result.scalar_one_or_none()
    
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Get user
    query = select(User).where(User.id == reset_token.user_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = get_password_hash(new_password)
    
    # Mark token as used
    reset_token.used = True
    
    await db.commit()


async def create_password_reset_token(db: AsyncSession, email: str) -> str:
    """Create a password reset token for the user."""
    user = await get_user_by_email(db, email)
    if not user:
        # Still create a dummy token to prevent timing attacks
        return create_token_for_email(email)
    
    return create_token_for_email(email, user.id)

def create_token_for_email(email: str, user_id: int = None) -> str:
    """Create a JWT token for password reset."""
    expires = datetime.utcnow() + timedelta(hours=24)
    data = {
        "sub": str(user_id) if user_id else "dummy",
        "email": email,
        "exp": expires
    }
    return jwt.encode(data, settings.secret_key, algorithm=settings.algorithm)

async def verify_reset_token(token: str) -> int:
    """Verify the reset token and return the user ID."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = payload.get("sub")
        if user_id == "dummy":
            raise ValueError("Invalid token")
        return int(user_id)
    except (jwt.JWTError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        ) from e

async def reset_password(db: AsyncSession, user_id: int, new_password: str) -> None:
    """Reset the user's password."""
    async with db.begin():
        user = await db.get(User, user_id)
        if not user:
            raise UserNotFoundError("User not found")
        user.hashed_password = get_password_hash(new_password)
        await db.commit()

async def get_user_by_email(db: AsyncSession, email: str) -> User:
    """Get user by email address."""
    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise UserNotFoundError(f"No user found with email: {email}")
    return user
