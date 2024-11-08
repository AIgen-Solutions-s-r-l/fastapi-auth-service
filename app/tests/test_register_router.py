# tests/test_register_router.py
import logging
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text
from app.core.config import Settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from app.core.security import get_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure test database
settings = Settings()
test_engine = create_async_engine(settings.test_database_url)
async_session_maker = async_sessionmaker(test_engine, expire_on_commit=False)


async def clear_tables():
    """Utility function to clear all tables"""
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))


@pytest_asyncio.fixture(scope="session")
async def init_db():
    """Create tables once for all tests"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def setup_test():
    """Reset database state before each test"""
    await clear_tables()
    yield


@pytest_asyncio.fixture
async def db_session():
    """Provide database session for each test"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    """Provide test client with database override"""

    async def override_get_db():
        try:
            yield db_session
        finally:
            pass  # Session closure is handled by db_session fixture

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


async def create_test_user(session: AsyncSession, username: str, email: str, password: str):
    """Helper function to create a test user"""
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password)
    )
    session.add(user)
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_register_user_success(client):
    """Test successful user registration"""
    payload = {
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    }

    response = await client.post("/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json() == {
        "message": "User registered successfully",
        "user": "testuser"
    }


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