"""Test configuration and fixtures."""

import asyncio
import uuid
import pytest
from typing import AsyncGenerator, Generator
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import declarative_base

from app.core.database import get_db
from app.main import app
from app.models.user import Base

# Use SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Create async engine for tests
engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,  # Disable SQL echo for cleaner test output
    connect_args={"check_same_thread": False}
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session")
@pytest.mark.asyncio(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for a test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    # Clean up after test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def test_app(db_session: AsyncSession) -> FastAPI:
    """Create a test instance of the FastAPI application."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
async def async_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def test_user(async_client: AsyncClient):
    """Create a test user with authentication token."""
    # Generate a unique username and email
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"
    
    # Register the user
    response = await async_client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert response.status_code == 201, "User registration failed"
    
    # Login to get a valid token
    login_response = await async_client.post("/auth/login", json={
        "username": username,
        "password": password
    })
    assert login_response.status_code == 200, "Login failed"
    
    data = login_response.json()
    token = data.get("access_token")
    assert token, "No access token in login response"
    
    user_data = {"username": username, "email": email, "password": password, "token": token}
    
    yield user_data
    
    # Cleanup: delete the user after tests run
    await async_client.delete(
        f"/auth/users/{username}",
        params={"password": password},
        headers={"Authorization": f"Bearer {token}"}
    )
