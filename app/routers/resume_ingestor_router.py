# app/tests/test_resume_ingestor_router.py

import asyncio
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.main import app
from app.models.user import User, Base

# Test data
VALID_RESUME_DATA = {
    "personal_information": {
        "name": "John",
        "surname": "Doe",
        "date_of_birth": "1990-01-01",
        "country": "USA",
        "city": "New York",
        "address": "123 Test St",
        "phone_prefix": "+1",
        "phone": "555-0123",
        "email": "john.doe@example.com",
        "github": "github.com/johndoe",
        "linkedin": "linkedin.com/in/johndoe"
    },
    "education_details": [{
        "education_level": "Bachelor's",
        "institution": "Test University",
        "field_of_study": "Computer Science",
        "final_evaluation_grade": "3.8",
        "start_date": "2010-09",
        "year_of_completion": "2014",
        "exam": {"course_name": "Final Project", "grade": "A"}
    }],
    "experience_details": [{
        "position": "Software Engineer",
        "company": "Tech Corp",
        "employment_period": "2014-2020",
        "location": "New York",
        "industry": "Technology",
        "key_responsibilities": ["Development", "Testing"],
        "skills_acquired": ["Python", "FastAPI"]
    }],
    "projects": [{
        "name": "Project X",
        "description": "A test project",
        "link": "github.com/project-x"
    }],
    "achievements": [{
        "name": "Best Developer",
        "description": "Won best developer award"
    }],
    "certifications": [{
        "name": "AWS Certified",
        "description": "AWS Developer Associate"
    }],
    "languages": [{
        "language": "English",
        "proficiency": "Native"
    }],
    "interests": ["Programming", "Reading"],
    "availability": {
        "notice_period": "2 weeks"
    },
    "salary_expectations": {
        "salary_range_usd": "80000-100000"
    },
    "self_identification": {
        "gender": "Male",
        "pronouns": "he/him",
        "veteran": "No",
        "disability": "No",
        "ethnicity": "Not specified"
    },
    "legal_authorization": {
        "eu_work_authorization": "Yes",
        "us_work_authorization": "No",
        "requires_us_visa": "No",
        "requires_us_sponsorship": "No",
        "requires_eu_visa": "No",
        "legally_allowed_to_work_in_eu": "Yes",
        "legally_allowed_to_work_in_us": "No",
        "requires_eu_sponsorship": "No",
        "canada_work_authorization": "No",
        "requires_canada_visa": "No",
        "legally_allowed_to_work_in_canada": "No",
        "requires_canada_sponsorship": "No",
        "uk_work_authorization": "No",
        "requires_uk_visa": "No",
        "legally_allowed_to_work_in_uk": "No",
        "requires_uk_sponsorship": "No"
    },
    "work_preferences": {
        "remote_work": "Yes",
        "in_person_work": "No",
        "open_to_relocation": "Yes",
        "willing_to_complete_assessments": "Yes",
        "willing_to_undergo_drug_tests": "Yes",
        "willing_to_undergo_background_checks": "Yes"
    }
}

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://testuser:testpassword@localhost:5432/main_db"


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app_instance() -> FastAPI:
    """Get FastAPI application instance."""
    return app


@pytest.fixture
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def test_session(test_engine) -> AsyncSession:
    """Create test database session."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def mongo_mock():
    """Mock MongoDB collection."""
    with patch('app.services.resume_service.collection_name') as mock:
        yield mock


@pytest.fixture
async def test_user(test_session: AsyncSession):
    """Create a test user."""
    from app.core.security import get_password_hash

    test_user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123")
    )

    test_session.add(test_user)
    await test_session.commit()
    await test_session.refresh(test_user)

    try:
        yield test_user
    finally:
        await test_session.delete(test_user)
        await test_session.commit()


@pytest.fixture
async def test_admin_user(test_session: AsyncSession):
    """Create a test admin user."""
    from app.core.security import get_password_hash

    admin_user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        is_admin=True
    )

    test_session.add(admin_user)
    await test_session.commit()
    await test_session.refresh(admin_user)

    try:
        yield admin_user
    finally:
        await test_session.delete(admin_user)
        await test_session.commit()


@pytest.fixture
async def client(app_instance: FastAPI, test_session: AsyncSession) -> AsyncClient:
    """Create test client with database session."""
    app_instance.dependency_overrides[get_db] = lambda: test_session
    async with AsyncClient(app=app_instance, base_url="http://test") as client:
        try:
            yield client
        finally:
            app_instance.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client: AsyncClient, test_user: User) -> AsyncClient:
    """Create authenticated test client."""
    from app.core.security import create_access_token

    access_token = create_access_token(data={"sub": test_user.username})
    client.headers["Authorization"] = f"Bearer {access_token}"
    return client


@pytest.fixture
async def admin_client(client: AsyncClient, test_admin_user: User) -> AsyncClient:
    """Create authenticated admin test client."""
    from app.core.security import create_access_token

    access_token = create_access_token(data={"sub": test_admin_user.username})
    client.headers["Authorization"] = f"Bearer {access_token}"
    return client


@pytest.mark.asyncio
async def test_create_resume_success(auth_client: AsyncClient, test_user: User, mongo_mock):
    """Test successful resume creation."""
    # Mock MongoDB response
    mongo_mock.insert_one.return_value.inserted_id = "test_id"
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await auth_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA,
            "user_id": test_user.id
        }
    )

    assert response.status_code == 201
    assert "personal_information" in response.json()
    assert response.json()["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_create_resume_invalid_data(auth_client: AsyncClient, test_user: User):
    """Test resume creation with invalid data."""
    invalid_data = {
        "personal_information": {
            "name": "John"  # Missing required fields
        },
        "user_id": test_user.id
    }

    response = await auth_client.post(
        "/resumes/create_resume",
        json=invalid_data
    )

    assert response.status_code == 400
    assert "Invalid resume data" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_get_resume_success(auth_client: AsyncClient, test_user: User, mongo_mock):
    """Test successful resume retrieval."""
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await auth_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 200
    assert response.json()["message"] == "Resume retrieved successfully"
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_get_resume_not_found(auth_client: AsyncClient, test_user: User, mongo_mock):
    """Test resume retrieval when resume doesn't exist."""
    mongo_mock.find_one.return_value = {"error": f"Resume not found for user ID: {test_user.id}"}

    response = await auth_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 404
    assert "ResumeNotFound" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_get_resume_unauthorized(auth_client: AsyncClient, test_user: User):
    """Test resume retrieval for unauthorized user."""
    other_user_id = test_user.id + 1

    response = await auth_client.get(f"/resumes/{other_user_id}")

    assert response.status_code == 403
    assert "NotAuthorized" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_admin_access_other_resume(admin_client: AsyncClient, test_user: User, mongo_mock):
    """Test admin access to other user's resume."""
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await admin_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 200
    assert response.json()["message"] == "Resume retrieved successfully"


@pytest.mark.asyncio
async def test_create_resume_nonexistent_user(auth_client: AsyncClient):
    """Test resume creation for non-existent user."""
    nonexistent_user_id = 99999

    response = await auth_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA,
            "user_id": nonexistent_user_id
        }
    )

    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_get_resume_with_version(auth_client: AsyncClient, test_user: User, mongo_mock):
    """Test resume retrieval with specific version."""
    mock_resume = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id,
        "version": "1.0"
    }
    mongo_mock.find_one.return_value = mock_resume

    response = await auth_client.get(
        f"/resumes/{test_user.id}",
        params={"version": "1.0"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["version"] == "1.0"