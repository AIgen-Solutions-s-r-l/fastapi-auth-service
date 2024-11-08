from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.security import verify_password
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
        ValueError: If the username already exists.
    """
    result = await db.execute(select(User).filter(User.username == username))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise ValueError("Username already exists")

    hashed_password = hash_password(password)
    new_user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def get_user_by_username(db: AsyncSession, username: str) -> dict | None:
    """
    Retrieve a user by username using a raw SQL query and return the user data as JSON.

    Args:
        db (AsyncSession): The database session.
        username (str): The username to look up.

    Returns:
        dict | None: The user data as a JSON-serializable dictionary if found, None otherwise.
    """
    query = text("SELECT * FROM users WHERE username = :username")
    result = await db.execute(query, {"username": username})
    user = result.fetchone()

    if user:
        # Convert SQLAlchemy Row object to dictionary
        user_dict = dict(user)
        # Convert to JSON-serializable dictionary
        return jsonable_encoder(user_dict)
    return None
