# app/tests/test_auth_router.py

import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.main import app

# Global test client
test_client = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
async def db_session():
    """
    Provides a managed database session for the tests.
    """
    DATABASE_URL = "postgresql+asyncpg://testuser:testpassword@localhost:5432/main_db"
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
async def override_dependency(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_user(async_client, db_session):
    """
    Test user registration.
    """
    user_data = {
        "username": "unique_test_user",
        "email": "unique_test_user@example.com",
        "password": "testpassword123"
    }

    # Cleanup any existing test user
    async with db_session.begin():
        await db_session.execute(
            text("DELETE FROM users WHERE username = :username"),
            {"username": user_data["username"]}
        )
        await db_session.commit()

    response = await async_client.post("/auth/register", json=user_data)
    assert response.status_code == 201
    assert response.json() == {"message": "User registered successfully", "username": user_data["username"]}


@pytest.mark.asyncio
async def test_login_user(async_client, db_session):
    """
    Test user login.
    """
    from app.core.security import get_password_hash

    user_data = {
        "username": "login_test_user",
        "email": "login_test_user@example.com",
        "password": "securepassword"
    }

    # Insert test user with hashed password
    async with db_session.begin():
        hashed_password = get_password_hash(user_data["password"])
        await db_session.execute(
            text("DELETE FROM users WHERE username = :username"),
            {"username": user_data["username"]}
        )
        await db_session.execute(
            text("""
                INSERT INTO users (username, email, hashed_password, is_admin)
                VALUES (:username, :email, :hashed_password, :is_admin)
                ON CONFLICT (username) DO NOTHING
            """),
            {
                "username": user_data["username"],
                "email": user_data["email"],
                "hashed_password": hashed_password,
                "is_admin": False
            }
        )
        await db_session.commit()

    # Send the login request with form data
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }

    response = await async_client.post(
        "/auth/login",
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 200
    token_response = response.json()
    assert "access_token" in token_response
    assert token_response["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_get_user_details(async_client, db_session):
    """
    Test user details retrieval.
    """
    from app.core.security import get_password_hash

    user_data = {
        "username": "details_test_user",
        "email": "details_test_user@example.com",
        "password": "testpassword123"
    }

    # Insert test user with hashed password
    async with db_session.begin():
        hashed_password = get_password_hash(user_data["password"])
        await db_session.execute(
            text("DELETE FROM users WHERE username = :username"),
            {"username": user_data["username"]}
        )
        await db_session.execute(
            text("""
                INSERT INTO users (username, email, hashed_password, is_admin)
                VALUES (:username, :email, :hashed_password, :is_admin)
                ON CONFLICT (username) DO NOTHING
            """),
            {
                "username": user_data["username"],
                "email": user_data["email"],
                "hashed_password": hashed_password,
                "is_admin": False
            }
        )
        await db_session.commit()

    response = await async_client.get(f"/auth/users/{user_data['username']}")
    assert response.status_code == 200
    user_details = response.json()
    assert user_details["username"] == user_data["username"]
    assert user_details["email"] == user_data["email"]
    assert "id" in user_details
    assert "hashed_password" not in user_details