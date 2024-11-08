# tests/test_auth_router.py
import logging

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.security import get_password_hash, verify_jwt_token
from app.main import app
from app.models.user import User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure test database
settings = Settings()
test_engine = create_async_engine(
    settings.test_database_url,
    echo=True,
    isolation_level="AUTOCOMMIT"  # Helps with transaction management
)

AsyncSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Initialize the test database"""
    logger.info("Setting up test database...")

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)  # Ensure clean state
        await conn.run_sync(Base.metadata.create_all)

        # Verify table creation
        result = await conn.execute(text("SELECT to_regclass('public.users')"))
        table_name = result.scalar()
        assert table_name == 'users', f"Expected 'users' table, got {table_name}"

    yield

    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Test database cleanup complete")


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_database):
    """Provide a database session for each test"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.flush()  # Ensure all SQL is executed
        finally:
            await session.rollback()  # Rollback any uncommitted changes
            await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    """Provide an HTTP test client with DB session override"""

    async def override_get_db():
        try:
            yield db_session
        finally:
            await db_session.close()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def create_test_user(db: AsyncSession, username: str, email: str, password: str):
    """Helper to create a test user"""
    try:
        hashed_password = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except Exception as e:
        await db.rollback()
        raise e


@pytest.mark.asyncio
async def test_register_user_success(client, db_session):
    """Test successful user registration"""
    # Verify database setup
    async with test_engine.connect() as conn:
        result = await conn.execute(text("SELECT to_regclass('public.users')"))
        assert result.scalar() is not None, "Users table not found in test database"

    # Test data
    payload = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    }

    # Execute test
    response = await client.post("/auth/register", json=payload)

    # Verify response
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    assert response.json() == {
        "message": "User registered successfully",
        "user": "testuser"
    }

    # Verify database state
    user_query = await db_session.execute(
        select(User).where(User.username == "testuser")
    )
    user = user_query.scalar_one_or_none()
    assert user is not None, "User was not created in database"
    assert user.email == "testuser@example.com"


@pytest.mark.asyncio
async def test_register_user_duplicate_username(client, db_session):
    """Test registration with duplicate username"""
    # Create initial user
    await create_test_user(
        db_session,
        username="existinguser",
        email="existing@example.com",
        password="password123"
    )

    # Attempt to create duplicate
    payload = {
        "username": "existinguser",
        "email": "new@example.com",
        "password": "newpassword"
    }

    response = await client.post("/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json() == {"detail": "Username already exists"}


@pytest.mark.asyncio
async def test_login_success(client, db_session):
    """Test successful login with correct credentials"""
    # First create a test user
    test_username = "testuser"
    test_password = "testpassword"
    await create_test_user(
        db_session,
        username=test_username,
        email="test@example.com",
        password=test_password
    )

    # Login data
    form_data = {
        "username": test_username,
        "password": test_password,
    }

    # Attempt login
    response = await client.post(
        "/auth/login",
        data=form_data,  # Note: using data instead of json for form data
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify token is valid
    token = data["access_token"]
    payload = verify_jwt_token(token)
    assert payload["sub"] == test_username


@pytest.mark.asyncio
async def test_login_invalid_credentials(client, db_session):
    """Test login with invalid credentials"""
    # Create test user
    await create_test_user(
        db_session,
        username="testuser",
        email="test@example.com",
        password="correctpassword"
    )

    # Try login with wrong password
    form_data = {
        "username": "testuser",
        "password": "wrongpassword",
    }

    response = await client.post(
        "/auth/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client, db_session):
    """Test login with non-existent user"""
    form_data = {
        "username": "nonexistentuser",
        "password": "anypassword",
    }

    response = await client.post(
        "/auth/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"