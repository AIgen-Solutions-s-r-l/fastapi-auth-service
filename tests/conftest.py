"""Common test fixtures and configurations."""

import pytest
from httpx import AsyncClient # Changed from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator, Generator, Tuple, Dict # Added Tuple, Dict
from unittest.mock import AsyncMock, patch
import asyncio
import secrets # Added secrets
import greenlet
import logging
from app.log.logging import logger # Import logger

from app.core.database import get_db
# Import app directly from app.main to ensure we're using the same instance
from app.main import app as app_instance
import app.models # Import all models to ensure they are registered with Base.metadata
from app.models.user import User # Ensure User is imported for type hinting
from app.core.base_model import Base # Import Base from its actual definition location
from app.services.email_service import EmailService

logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# Use SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Create engine once
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    # poolclass=None, # Let SQLAlchemy manage pooling, default is QueuePool
    echo=False # Set to True for debugging SQL
)

# Create sessionmaker once
AsyncTestingSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Create database tables once per session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all) # Drop at start of session
        await conn.run_sync(Base.metadata.create_all) # Create at start of session
    logger.info("Database tables created for test session.")
    yield
    logger.info("Test session finished.")
    # Optional: Drop tables at end of session if needed
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture()
async def db(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a test using nested transactions."""
    async with AsyncTestingSessionLocal() as session:
        # Begin a nested transaction (savepoint) for the test
        nested_transaction = await session.begin_nested()
        logger.debug(f"Started nested transaction for test.")

        yield session

        # Roll back the nested transaction after the test
        if nested_transaction.is_active:
            await nested_transaction.rollback()
            logger.debug(f"Rolled back nested transaction.")
        else:
            logger.warning(f"Nested transaction was already inactive before explicit rollback.")
        # The outer transaction managed by AsyncTestingSessionLocal context manager
        # will also be rolled back upon exiting the 'async with'.

@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]: # Changed to async fixture and AsyncClient
    """Create an async test client with a clean database."""
    
    async def override_get_db():
        yield db # Simplified: db fixture manages its own lifecycle
 
    app_instance.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app_instance, base_url="http://test") as test_client: # Use app_instance
        yield test_client
    app_instance.dependency_overrides.clear()

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
async def create_test_user(db: AsyncSession, email: str, password: str, is_verified: bool = False) -> User: # Added return type hint
    """Helper function to create a test user."""
    from app.services.user_service import UserService # Changed from create_user directly
    user_service = UserService(db) # Instantiate UserService
    user = await user_service.create_user(email, password, auto_verify=is_verified) # Call the method
    # Removed direct is_verified assignment and commit, as create_user handles it.
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

@pytest.fixture
async def auth_user_and_header(db: AsyncSession) -> Tuple[User, Dict[str, str]]:
    """Create an authenticated user and return the user object and auth header."""
    from app.core.security import create_access_token
    from datetime import timedelta

    # Create a unique email for each test run using this fixture
    unique_suffix = secrets.token_hex(4)
    test_email = f"auth_test_{unique_suffix}@example.com"
    
    # Create a test user
    user = await create_test_user(db, test_email, "password123", is_verified=True)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": user.email}, # Use the actual email of the created user
        expires_delta=timedelta(minutes=30)
    )
    
    auth_header_dict = {"Authorization": f"Bearer {access_token}"}
    return user, auth_header_dict