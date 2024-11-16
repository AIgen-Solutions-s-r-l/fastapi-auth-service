# app/tests/test_resume_ingestor_router.py

import pytest
from unittest.mock import Mock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.main import app
from app.core.database import get_db
from app.core.mongodb import collection_name
from app.models.user import User

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


@pytest.fixture
def mongo_mock():
    with patch('app.services.resume_service.collection_name') as mock:
        yield mock


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Create test database and tables"""
    from app.models.user import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    TEST_DATABASE_URL = "postgresql+asyncpg://testuser:testpassword@localhost:5432/main_db"
    engine = create_async_engine(TEST_DATABASE_URL)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Override the database dependency
    async def get_test_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = get_test_db

    yield

    # Clean up
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def test_user(setup_test_db):
    """Create a test user"""
    from app.core.security import get_password_hash

    async def get_session():
        for session in setup_test_db:
            yield session

    db = await anext(get_session())

    # Create test user
    hashed_password = get_password_hash("testpassword123")
    test_user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hashed_password
    )

    db.add(test_user)
    await db.commit()
    await db.refresh(test_user)

    yield test_user

    # Cleanup
    await db.delete(test_user)
    await db.commit()


@pytest.fixture
async def authenticated_client(test_user):
    """Create an authenticated client for testing protected endpoints"""
    from app.core.security import create_access_token

    access_token = create_access_token(data={"sub": test_user.username})
    headers = {"Authorization": f"Bearer {access_token}"}

    async with AsyncClient(app=app, base_url="http://test", headers=headers) as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_resume_success(authenticated_client, mongo_mock, test_user):
    """Test successful resume creation"""
    # Mock MongoDB response
    mongo_mock.insert_one.return_value.inserted_id = "test_id"
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await authenticated_client.post(
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
async def test_create_resume_invalid_data(authenticated_client, mongo_mock, test_user):
    """Test resume creation with invalid data"""
    invalid_data = {
        "personal_information": {
            "name": "John"  # Missing required fields
        },
        "user_id": test_user.id
    }

    response = await authenticated_client.post(
        "/resumes/create_resume",
        json=invalid_data
    )

    assert response.status_code == 400
    assert "Invalid resume data" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_get_resume_success(authenticated_client, mongo_mock, test_user):
    """Test successful resume retrieval"""
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await authenticated_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 200
    assert response.json()["message"] == "Resume retrieved successfully"
    assert "data" in response.json()


@pytest.mark.asyncio
async def test_get_resume_not_found(authenticated_client, mongo_mock, test_user):
    """Test resume retrieval when resume doesn't exist"""
    mongo_mock.find_one.return_value = None

    response = await authenticated_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 404
    assert "ResumeNotFound" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_get_resume_unauthorized(authenticated_client, mongo_mock, test_user):
    """Test resume retrieval for unauthorized user"""
    # Try to access another user's resume
    other_user_id = test_user.id + 1

    response = await authenticated_client.get(f"/resumes/{other_user_id}")

    assert response.status_code == 403
    assert "NotAuthorized" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_create_resume_nonexistent_user(authenticated_client, mongo_mock):
    """Test resume creation for non-existent user"""
    nonexistent_user_id = 99999

    response = await authenticated_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA,
            "user_id": nonexistent_user_id
        }
    )

    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_get_resume_with_version(authenticated_client, mongo_mock, test_user):
    """Test resume retrieval with specific version"""
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id,
        "version": "1.0"
    }

    response = await authenticated_client.get(
        f"/resumes/{test_user.id}",
        params={"version": "1.0"}
    )

    assert response.status_code == 200
    assert response.json()["data"]["version"] == "1.0"