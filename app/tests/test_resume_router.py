# tests/test_resume_router.py
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import Settings
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User

# Configure test database
settings = Settings()
test_engine = create_async_engine(
    settings.test_database_url,
    echo=True,
    isolation_level="AUTOCOMMIT"
)

AsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Test data
SAMPLE_RESUME = {
    "user_id": "1",
    "name": "John Doe",
    "email": "john@example.com",
    "experience": [
        {
            "company": "Tech Corp",
            "position": "Developer",
            "years": 2
        }
    ],
    "education": [
        {
            "school": "University",
            "degree": "Computer Science",
            "year": 2020
        }
    ],
    "skills": ["Python", "FastAPI", "MongoDB"]
}


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Initialize the test database"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_database):
    """Provide a database session for each test"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.flush()
        finally:
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture
async def client(db_session):
    """Provide a test client with DB session override"""

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


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user in the database"""
    user = User(username="testuser", email="test@example.com",hashed_password="securepassword")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_resume_success(client, test_user):
    """Test successful resume creation"""
    # Mock MongoDB response
    mock_mongo_response = {"_id": "some_id", **SAMPLE_RESUME}

    with patch('app.core.mongodb.add_resume', return_value=mock_mongo_response):
        response = await client.post(
            "/resume/create_resume",
            json=SAMPLE_RESUME
        )

        assert response.status_code == 200
        data = response.json()
        assert data["_id"] == "some_id"
        assert data["name"] == SAMPLE_RESUME["name"]
        assert data["email"] == SAMPLE_RESUME["email"]


@pytest.mark.asyncio
async def test_create_resume_user_not_found(client):
    """Test resume creation with non-existent user"""
    # Use a non-existent user ID
    resume_data = {**SAMPLE_RESUME, "user_id": "999"}

    response = await client.post(
        "/resume/create_resume",
        json=resume_data
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_create_resume_mongodb_error(client, test_user):
    """Test resume creation with MongoDB error"""
    # Mock MongoDB error response
    with patch('app.core.mongodb.add_resume', return_value={"error": "MongoDB error"}):
        response = await client.post(
            "/resume/create_resume",
            json=SAMPLE_RESUME
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "MongoDB error"


@pytest.mark.asyncio
async def test_get_resume_success(client):
    """Test successful resume retrieval"""
    # Mock MongoDB response for get_resume
    mock_resume = {"_id": "some_id", **SAMPLE_RESUME}

    with patch('app.core.mongodb.get_resume_by_user_id', return_value=mock_resume):
        response = await client.get(f"/resume/resume/{SAMPLE_RESUME['user_id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["_id"] == "some_id"
        assert data["name"] == SAMPLE_RESUME["name"]
        assert data["email"] == SAMPLE_RESUME["email"]


@pytest.mark.asyncio
async def test_get_resume_not_found(client):
    """Test resume retrieval for non-existent resume"""
    # Mock MongoDB error response
    with patch('app.core.mongodb.get_resume_by_user_id', return_value={"error": "Resume not found"}):
        response = await client.get("/resume/resume/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Resume not found"


@pytest.mark.asyncio
async def test_create_resume_invalid_data(client, test_user):
    """Test resume creation with invalid data"""
    invalid_resume = {
        "user_id": "1",
        "name": "John Doe",
        # Missing required fields
    }

    response = await client.post(
        "/resume/create_resume",
        json=invalid_resume
    )

    assert response.status_code == 422  # Validation error
