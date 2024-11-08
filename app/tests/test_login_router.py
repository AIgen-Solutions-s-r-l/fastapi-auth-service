# tests/test_login_router.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.main import app
from app.models.user import User

# Configure test database
settings = Settings()
test_engine = create_async_engine(
    settings.test_database_url,
    isolation_level="AUTOCOMMIT"
)

AsyncSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """
    Create and drop test database tables between each test.
    The autouse=True makes this fixture run automatically for each test.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    """Provide a database session for each test"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    """Provide a test client with DB session override"""

    async def override_get_db():
        try:
            yield db_session
        finally:
            await db_session.close()  # Changed from session to db_session

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
async def test_login_success(client, db_session):
    """Test successful login"""
    # Create test user
    test_username = "testuser"
    test_password = "testpassword"
    await create_test_user(
        db_session,
        username=test_username,
        email="test@example.com",
        password=test_password
    )

    # Try to login
    form_data = {
        "username": test_username,
        "password": test_password,
        "grant_type": "password"  # Add this line
    }

    response = await client.post(
        "/auth/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client, db_session):
    """Test login with wrong password"""
    username = "testuser2"
    await create_test_user(
        db_session,
        username=username,
        email="test@example.com",
        password="correctpassword"
    )

    form_data = {
        "username": username,
        "password": "wrongpassword",
        "grant_type": "password"  # Add this line
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
        "grant_type": "password"  # Add this line
    }

    response = await client.post(
        "/auth/login",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"
