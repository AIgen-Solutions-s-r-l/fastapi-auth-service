import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import Settings
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.core.security import get_password_hash


@pytest_asyncio.fixture(scope="function")
async def client():
    # Provides a client bound to the test app instance using ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def create_test_user(db: AsyncSession, username: str, email: str, password: str):
    # Helper to create a test user in the database
    hashed_password = get_password_hash(password)
    user = User(username=username, email=email, hashed_password=hashed_password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio(loop_scope="function")
async def test_register_user_success(client, test_db):
    payload = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    }
    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 201
    assert response.json() == {"message": "User registered successfully", "user": "testuser"}
