"""Fixtures for auth router tests."""

import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.database import get_db
from app.models.user import User
from app.core.security import create_access_token
from app.services.user_service import UserService # Changed import
from datetime import timedelta, datetime, timezone

# Create a test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

@pytest.fixture
async def db():
    """Create a fresh database for each test."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.create_all)
    
    # Create a session
    async with TestingSessionLocal() as session:
        yield session
    
    # Drop tables after test
    async with engine.begin() as conn:
        await conn.run_sync(User.metadata.drop_all)

@pytest.fixture
def client(db):
    """Create a test client with a test database."""
    async def override_get_db():
        yield db
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    
    # Reset dependency overrides
    app.dependency_overrides = {}

@pytest.fixture
async def test_user(db):
    """Create a test user."""
    user_data = {
        "email": "test@example.com",
        "password": "password123"
    }
    
    # Create the user
    user_service = UserService(db)
    user = await user_service.create_user(user_data["email"], user_data["password"])
    
    # Set the user as verified
    user.is_verified = True
    await db.commit()
    
    return user_data

@pytest.fixture
def test_user_token(test_user):
    """Create a token for the test user."""
    # Calculate expiration time using timezone-aware datetime
    expires_delta = timedelta(minutes=60)
    expire_time = datetime.now(timezone.utc) + expires_delta
    
    # Create token
    access_token = create_access_token(
        data={
            "sub": test_user["email"],
            "id": 1,  # Assuming the first user has ID 1
            "is_admin": False,
            "exp": expire_time.timestamp()
        },
        expires_delta=expires_delta
    )
    
    return access_token

@pytest.fixture
async def test_admin_user(db):
    """Create a test admin user."""
    user_data = {
        "email": "admin@example.com",
        "password": "adminpass123"
    }
    
    # Create the user
    user_service = UserService(db)
    user = await user_service.create_user(user_data["email"], user_data["password"])
    
    # Set the user as verified and admin
    user.is_verified = True
    user.is_admin = True
    await db.commit()
    
    return user_data

@pytest.fixture
def test_admin_token(test_admin_user):
    """Create a token for the test admin user."""
    # Calculate expiration time using timezone-aware datetime
    expires_delta = timedelta(minutes=60)
    expire_time = datetime.now(timezone.utc) + expires_delta
    
    # Create token
    access_token = create_access_token(
        data={
            "sub": test_admin_user["email"],
            "id": 2,  # Assuming the second user has ID 2
            "is_admin": True,
            "exp": expire_time.timestamp()
        },
        expires_delta=expires_delta
    )
    
    return access_token

@pytest.fixture
async def test_user_with_profile_data(db):
    """Create a test user with profile data for status API tests."""
    user_data = {
        "email": "statususer@example.com",
        "password": "statuspassword"
    }
    
    # Create the user
    user_service = UserService(db)
    user = await user_service.create_user(user_data["email"], user_data["password"])
    
    # Set the user as verified
    user.is_verified = True
    user.account_status = "active"
    user.has_consumed_initial_trial = False
    user.stripe_customer_id = "cus_test_status"
    
    await db.commit()
    await db.refresh(user)
    
    return user