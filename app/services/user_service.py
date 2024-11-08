from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.core.security import hash_password
from sqlalchemy.future import select


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
