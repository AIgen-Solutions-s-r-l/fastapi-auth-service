"""Common test fixtures and configurations."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, patch
import asyncio
import greenlet
import logging

from app.core.database import get_db
from app.main import app
from app.models.user import Base
from app.services.email_service import EmailService

logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Use SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False},
    poolclass=None,
    echo=False
)
TestingSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession,
    expire_on_commit=False
)

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Create a clean database session for a test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()
        await session.close()

@pytest.fixture
def client(db: AsyncSession) -> Generator:
    """Create a test client with a clean database."""
    
    async def override_get_db():
        try:
            yield db
        finally:
            await db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def test_user_data():
    """Test user data fixture."""
    return {
        "email": "test@example.com",
        "password": "testpassword123"
    }

@pytest.fixture(autouse=True)
def mock_email_service():
    """Mock email service for all tests."""
    with patch.object(EmailService, 'send_registration_confirmation', new_callable=AsyncMock) as mock_reg:
        with patch.object(EmailService, 'send_welcome_email', new_callable=AsyncMock) as mock_welcome:
            with patch.object(EmailService, 'send_password_change_confirmation', new_callable=AsyncMock) as mock_password:
                with patch.object(EmailService, '_send_templated_email', new_callable=AsyncMock) as mock_template:
                    mock_reg.return_value = True
                    mock_welcome.return_value = True
                    mock_password.return_value = True
                    mock_template.return_value = True
                    yield {
                        'registration': mock_reg,
                        'welcome': mock_welcome,
                        'password': mock_password,
                        'template': mock_template
                    }

@pytest.fixture
def mock_background_tasks():
    """Mock background tasks."""
    with patch('fastapi.BackgroundTasks.add_task') as mock:
        yield mock

# Helper functions for tests
async def create_test_user(db: AsyncSession, email: str, password: str, is_verified: bool = False):
    """Helper function to create a test user."""
    from app.services.user_service import create_user
    user = await create_user(db, email, password)
    if is_verified:
        user.is_verified = True
        await db.commit()
    return user

async def create_test_token(db: AsyncSession, user_id: int, token: str, expires_in_hours: int = 24):
    """Helper function to create a test token."""
    from datetime import datetime, timedelta, timezone
    from app.models.user import EmailVerificationToken
    
    token_record = EmailVerificationToken(
        token=token,
        user_id=user_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        used=False
    )
    db.add(token_record)
    await db.commit()
    return token_record