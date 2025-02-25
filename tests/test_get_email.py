"""Tests for email retrieval endpoints."""

import pytest
from httpx import AsyncClient
from app.main import app
from app.services.user_service import create_user
from app.core.database import get_db

@pytest.fixture(autouse=True)
def override_get_db(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
async def new_user(db_session):
    """Create a test user."""
    user = await create_user(db_session, "testuser", "test@example.com", "password123")
    await db_session.commit()
    return user

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_get_email_existing(new_user, async_client):
    """Test getting email for an existing user."""
    response = await async_client.get(f"/auth/users/{new_user.id}/email")
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_get_email_not_found(async_client):
    """Test getting email for a non-existent user."""
    response = await async_client.get("/auth/users/999999/email")
    assert response.status_code == 404