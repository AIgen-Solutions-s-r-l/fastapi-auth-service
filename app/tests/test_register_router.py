# tests/test_register_router.py
import logging
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import sessionmaker
from app.core.config import Settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.security import get_password_hash
from sqlalchemy import text, select

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure test database
settings = Settings()
test_engine = create_async_engine(
    settings.test_database_url,
    isolation_level="AUTOCOMMIT"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def create_tables():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def cleanup_tables(create_tables):
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))


@pytest.fixture
async def db_session():
    """Create a fresh database session for each test"""
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
async def client(db_session):
    """Provide a test client with DB session override"""

    async def override_get_db():
        try:
            yield db_session
        finally:
            await db_session.rollback()

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


async def create_test_user(session: AsyncSession, username: str, email: str, password: str):
    """Helper to create a test user"""
    try:
        hashed_password = get_password_hash(password)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except Exception:
        await session.rollback()
        raise


@pytest.mark.asyncio
async def test_register_user_success(client, db_session):
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

    result = await db_session.execute(
        select(User).where(User.username == "testuser")
    )
    user = result.scalar_one_or_none()
    assert user is not None
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