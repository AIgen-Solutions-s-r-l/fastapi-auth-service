# tests/test_register_router.py
import logging
import pytest
import pytest_asyncio
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
test_engine = create_async_engine(settings.test_database_url)

# Create async session factory
async_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Create the test database tables once for all tests"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_db):
    """Create a fresh database session for each test"""
    async with async_session_maker() as session:
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """Provide a test client with DB session override"""

    async def override_get_db():
        yield db_session

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

    # Verify in database
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