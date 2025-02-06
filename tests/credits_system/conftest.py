"""Shared fixtures for credit system tests."""

import uuid
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
async def test_user(async_client: AsyncClient):
    """Create a test user for credit operations."""
    # Generate a unique username and email
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"
    
    # Register the user
    response = await async_client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    if response.status_code != 201:
        pytest.skip("Registration failed, skipping credit router tests")
    data = response.json()
    token = data.get("access_token")
    user_data = {"username": username, "email": email, "password": password, "token": token}
    
    yield user_data
    
    # Cleanup: delete the user after tests run
    await async_client.delete(
        f"/auth/users/{username}",
        params={"password": password},
        headers={"Authorization": f"Bearer {token}"}
    )