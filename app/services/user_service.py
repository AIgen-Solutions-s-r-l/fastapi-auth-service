# app/services/user_service.py
from typing import Dict, Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError, UserAlreadyExistsError, DatabaseOperationError
from app.core.security import verify_password, get_password_hash
from app.models.user import User


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
    """
    Creates a new user and saves it to the database.

    Args:
        db (AsyncSession): The database session.
        username (str): The username for the new user.
        email (str): The email for the new user.
        password (str): The plain text password for the new user.

    Returns:
        User: The created user.

    Raises:
        UserAlreadyExistsError: If the username or email already exists.
    """
    # Verifica username
    result = await db.execute(select(User).filter(User.username == username))
    if result.scalar_one_or_none():
        raise UserAlreadyExistsError(f"username: {username}")

    # Verifica email
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
        raise DatabaseOperationError(f"Error creating user: {str(e)}")


async def get_user_by_username(db: AsyncSession, username: str) -> Dict[str, Any]:
    """
    Retrieve a user by username using a raw SQL query and return the user data as JSON.

    This function uses a raw SQL query for demonstration purposes. In production,
    consider using SQLAlchemy's ORM features for better security and maintainability.

    Args:
        db (AsyncSession): The database session.
        username (str): The username to look up.

    Returns:
        Dict[str, Any]: The user data as a JSON-serializable dictionary.

    Raises:
        UserNotFoundError: If no user is found with the given username.
    """
    try:
        # Using parameterized query to prevent SQL injection
        query = text("SELECT * FROM users WHERE username = :username")
        result = await db.execute(query, {"username": username})
        user = result.fetchone()

        if not user:
            raise UserNotFoundError(f"username: {username}")

        # Convert SQLAlchemy Row object to dictionary and make it JSON-serializable
        user_dict = dict(user)
        return jsonable_encoder(user_dict)

    except Exception as e:
        # Log the error here if you have logging configured
        raise Exception(f"Error retrieving user: {str(e)}")


async def update_user_password(
        db: AsyncSession,
        username: str,
        current_password: str,
        new_password: str
) -> User:
    """
    Update a user's password after verifying their current password.

    Args:
        db (AsyncSession): The database session.
        username (str): The username of the user.
        current_password (str): The user's current password for verification.
        new_password (str): The new password to set.

    Returns:
        User: The updated user object.

    Raises:
        UserNotFoundError: If no user is found with the given username.
        InvalidCredentialsError: If the current password is incorrect.
    """
    user = await authenticate_user(db, username, current_password)

    try:
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as e:
        await db.rollback()
        raise Exception(f"Error updating password: {str(e)}")


async def delete_user(db: AsyncSession, username: str, password: str) -> None:
    """
    Delete a user after verifying their password.

    Args:
        db (AsyncSession): The database session.
        username (str): The username of the user to delete.
        password (str): The user's password for verification.

    Raises:
        UserNotFoundError: If no user is found with the given username.
        InvalidCredentialsError: If the password is incorrect.
    """
    user = await authenticate_user(db, username, password)

    try:
        await db.delete(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise Exception(f"Error deleting user: {str(e)}")
