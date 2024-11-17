# app/tests/test_resume_ingestor_router.py
import asyncio
from asyncio import get_event_loop_policy, new_event_loop
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth import get_current_user
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

# Test settings
TEST_DATABASE_URL = "postgresql+asyncpg://testuser:testpassword@localhost:5432/main_db"


# Fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create and provide an event loop for all async fixtures."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_db_session(test_engine):
    """Provide test database session."""
    TestingSessionLocal = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest.fixture(scope="function")
async def client(test_db_session):
    """Create test client with overridden database session."""
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: test_db_session

    # Use explicit ASGITransport
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def mongo_mock():
    """Mock MongoDB collection."""
    with patch('app.services.resume_service.collection_name') as mock:
        # Set up default async mocks for common operations
        mock.find_one = AsyncMock()
        mock.insert_one = AsyncMock()
        mock.find_one_and_update = AsyncMock()
        mock.delete_one = AsyncMock()
        yield mock


@pytest.fixture(scope="function")
async def test_user(test_db_session):
    """Create and provide a test user."""
    from app.core.security import get_password_hash

    test_user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpassword123"),
        is_admin=False
    )

    test_db_session.add(test_user)
    await test_db_session.commit()
    await test_db_session.refresh(test_user)

    try:
        yield test_user
    finally:
        await test_db_session.delete(test_user)
        await test_db_session.commit()


@pytest.fixture(scope="function")
async def test_admin_user(test_db_session):
    """Create and provide a test admin user."""
    from app.core.security import get_password_hash

    admin_user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass123"),
        is_admin=True
    )

    test_db_session.add(admin_user)
    await test_db_session.commit()
    await test_db_session.refresh(admin_user)

    try:
        yield admin_user
    finally:
        await test_db_session.delete(admin_user)
        await test_db_session.commit()


@pytest.fixture(scope="function")
async def auth_client(client, test_user):
    """Create authenticated test client."""
    from app.core.security import create_access_token

    # Create access token
    access_token = create_access_token(data={"sub": test_user.username})

    # Override both the database and auth dependencies
    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client.headers["Authorization"] = f"Bearer {access_token}"

    try:
        yield client
    finally:
        # Clean up overrides after test
        app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def admin_client(client, test_admin_user):
    """Create authenticated admin test client."""
    from app.core.security import create_access_token

    # Create access token
    access_token = create_access_token(data={"sub": test_admin_user.username})

    # Override both the database and auth dependencies
    async def override_get_current_user():
        return test_admin_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client.headers["Authorization"] = f"Bearer {access_token}"

    try:
        yield client
    finally:
        # Clean up overrides after test
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_resume_success(auth_client, mongo_mock, test_user):
    """Test successful resume creation."""
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
async def test_get_resume_success(auth_client, mongo_mock, test_user):
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
async def test_create_resume_invalid_data(auth_client, test_user):
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

    assert response.status_code == 422
    response_data = response.json()
    assert "error" in response_data
    assert "message" in response_data
    assert "details" in response_data
    assert any("Field required" in error["msg"] for error in response_data["details"])


@pytest.mark.asyncio
async def test_create_resume_unauthorized_user(auth_client, test_user):
    """Test resume creation for unauthorized user."""
    other_user_id = test_user.id + 1

    response = await auth_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA["personal_information"],  # Fix to send only personal_information
            "user_id": other_user_id
        }
    )

    assert response.status_code == 403
    assert "NotAuthorized" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_create_resume_as_admin(admin_client, mongo_mock, test_user):
    """Test resume creation by admin for another user."""
    # Setup mock to handle both the existence check and the retrieval
    find_one_mock = AsyncMock()
    find_one_mock.side_effect = [
        None,  # First call returns None (resume doesn't exist)
        {  # Second call returns the created resume
            "_id": "test_id",
            **VALID_RESUME_DATA,
            "user_id": test_user.id
        }
    ]
    mongo_mock.find_one = find_one_mock

    mongo_mock.insert_one.return_value.inserted_id = "test_id"

    response = await admin_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA["personal_information"],
            "user_id": test_user.id
        }
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_create_resume_success(auth_client, mongo_mock, test_user):
    """Test successful resume creation."""
    # Setup mock to handle both the existence check and the retrieval
    find_one_mock = AsyncMock()
    find_one_mock.side_effect = [
        None,  # First call returns None (resume doesn't exist)
        {  # Second call returns the created resume
            "_id": "test_id",
            **VALID_RESUME_DATA,
            "user_id": test_user.id
        }
    ]
    mongo_mock.find_one = find_one_mock

    mongo_mock.insert_one.return_value.inserted_id = "test_id"

    response = await auth_client.post(
        "/resumes/create_resume",
        json={
            "personal_information": VALID_RESUME_DATA["personal_information"],
            "user_id": test_user.id
        }
    )

    assert response.status_code == 201
    assert "personal_information" in response.json()
    assert response.json()["user_id"] == test_user.id


@pytest.mark.asyncio
async def test_get_resume_not_found(auth_client, mongo_mock, test_user):
    """Test resume retrieval when resume doesn't exist."""
    mongo_mock.find_one.return_value = {"error": f"Resume not found for user ID: {test_user.id}"}

    response = await auth_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 404
    assert "ResumeNotFound" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_get_resume_unauthorized(auth_client, mongo_mock, test_user):
    """Test resume retrieval for unauthorized user."""
    other_user_id = test_user.id + 1

    response = await auth_client.get(f"/resumes/{other_user_id}")

    assert response.status_code == 403
    assert "NotAuthorized" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_admin_get_any_resume(admin_client, mongo_mock, test_user):
    """Test admin access to any resume."""
    mongo_mock.find_one.return_value = {
        "_id": "test_id",
        **VALID_RESUME_DATA,
        "user_id": test_user.id
    }

    response = await admin_client.get(f"/resumes/{test_user.id}")

    assert response.status_code == 200
    assert response.json()["message"] == "Resume retrieved successfully"


@pytest.mark.asyncio
async def test_update_resume_success(auth_client, mongo_mock, test_user):
    """Test successful resume update."""
    updated_data = {
        **VALID_RESUME_DATA,
        "personal_information": {
            **VALID_RESUME_DATA["personal_information"],
            "position": "Senior Software Engineer"
        },
        "self_identification": {
            **VALID_RESUME_DATA["self_identification"],
            "veteran": VALID_RESUME_DATA["self_identification"]["veteran"] == "Yes",
            "disability": VALID_RESUME_DATA["self_identification"]["disability"] == "No"
        },
        "legal_authorization": {
            **VALID_RESUME_DATA["legal_authorization"],
            "eu_work_authorization": VALID_RESUME_DATA["legal_authorization"]["eu_work_authorization"] == "Yes",
            # ... (same boolean conversions as above)
            "requires_uk_sponsorship": VALID_RESUME_DATA["legal_authorization"]["requires_uk_sponsorship"] == "No"
        },
        "work_preferences": {
            **VALID_RESUME_DATA["work_preferences"],
            "remote_work": VALID_RESUME_DATA["work_preferences"]["remote_work"] == "Yes",
            # ... (same boolean conversions as above)
            "willing_to_undergo_background_checks": VALID_RESUME_DATA["work_preferences"][
                                                        "willing_to_undergo_background_checks"] == "Yes"
        },
        "user_id": test_user.id
    }

    mongo_mock.find_one_and_update.return_value = {
        "_id": "test_id",
        **updated_data
    }

    response = await auth_client.put(
        f"/resumes/{test_user.id}",
        json=updated_data
    )

    assert response.status_code == 200
    assert response.json()["personal_information"]["position"] == "Senior Software Engineer"


@pytest.mark.asyncio
async def test_delete_resume_success(auth_client, mongo_mock, test_user):
    """Test successful resume deletion."""
    # Set up the mock with proper async methods
    mock_find_one = AsyncMock()
    mock_find_one.return_value = {"_id": "test_id", "user_id": test_user.id}
    mongo_mock.find_one = mock_find_one

    mock_delete_one = AsyncMock()
    mock_delete_one.return_value.deleted_count = 1
    mongo_mock.delete_one = mock_delete_one

    response = await auth_client.delete(f"/resumes/{test_user.id}")

    assert response.status_code == 200
    assert response.json()["message"] == "Resume deleted successfully"


@pytest.mark.asyncio
async def test_delete_resume_not_found(auth_client, mongo_mock, test_user):
    """Test resume deletion when resume doesn't exist."""
    # Set up the mock with proper async methods
    mock_find_one = AsyncMock()
    mock_find_one.return_value = None
    mongo_mock.find_one = mock_find_one

    mock_delete_one = AsyncMock()
    mock_delete_one.return_value.deleted_count = 0
    mongo_mock.delete_one = mock_delete_one

    response = await auth_client.delete(f"/resumes/{test_user.id}")

    assert response.status_code == 404
    assert "ResumeNotFound" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_delete_resume_unauthorized(auth_client, test_user):
    """Test resume deletion by unauthorized user."""
    other_user_id = test_user.id + 1

    response = await auth_client.delete(f"/resumes/{other_user_id}")

    assert response.status_code == 403
    assert "NotAuthorized" in response.json()["detail"]["error"]
