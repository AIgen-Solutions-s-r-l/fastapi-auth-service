"""Test module for internal-only endpoints."""

import pytest
from httpx import AsyncClient
from fastapi import status

from app.core.config import settings


@pytest.mark.asyncio
async def test_get_email_by_user_id_without_api_key(async_client: AsyncClient, test_user, db_session):
    """Test that get_email_by_user_id rejects requests without API key."""
    # Get user by email from db to get the ID
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db_session.execute(select(User).where(User.email == test_user['email']))
    user = result.scalar_one_or_none()
    
    # Try to access without API key
    response = await async_client.get(f"/auth/users/{user.id}/email")
    
    # Should be rejected with a validation error (422) for missing required header
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # Verify that the error message mentions the api-key
    assert "api-key" in response.text.lower()
    

@pytest.mark.asyncio
async def test_get_email_by_user_id_with_invalid_api_key(async_client: AsyncClient, test_user, db_session):
    """Test that get_email_by_user_id rejects requests with invalid API key."""
    # Get user by email from db to get the ID
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db_session.execute(select(User).where(User.email == test_user['email']))
    user = result.scalar_one_or_none()
    
    # Try to access with invalid API key
    response = await async_client.get(
        f"/auth/users/{user.id}/email",
        headers={"api-key": "invalid-key"}
    )
    
    # Should be forbidden (403)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_email_by_user_id_with_valid_api_key(async_client: AsyncClient, test_user, db_session):
    """Test that get_email_by_user_id accepts requests with valid API key."""
    # Get user by email from db to get the ID
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db_session.execute(select(User).where(User.email == test_user['email']))
    user = result.scalar_one_or_none()
    
    # Access with valid API key
    response = await async_client.get(
        f"/auth/users/{user.id}/email",
        headers={"api-key": settings.INTERNAL_API_KEY}
    )
    
    # Should succeed (200)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "email" in data
    assert data["email"] == test_user['email']


@pytest.mark.asyncio
async def test_get_user_by_email_without_api_key(async_client: AsyncClient, test_user):
    """Test that get_user_details rejects requests without API key."""
    # Try to access without API key
    response = await async_client.get(f"/auth/users/by-email/{test_user['email']}")
    
    # Should be rejected (422 in this case because it's a FastAPI validation error for missing required header)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_get_user_by_email_with_invalid_api_key(async_client: AsyncClient, test_user):
    """Test that get_user_details rejects requests with invalid API key."""
    # Try to access with invalid API key
    response = await async_client.get(
        f"/auth/users/by-email/{test_user['email']}",
        headers={"api-key": "invalid-key"}
    )
    
    # Invalid credentials should be forbidden (403)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_user_by_email_with_valid_api_key(async_client: AsyncClient, test_user):
    """Test that get_user_details accepts requests with valid API key."""
    # Access with valid API key
    response = await async_client.get(
        f"/auth/users/by-email/{test_user['email']}",
        headers={"api-key": settings.INTERNAL_API_KEY}
    )
    
    # Should succeed (200)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "email" in data
    assert data["email"] == test_user['email']
    assert "is_verified" in data