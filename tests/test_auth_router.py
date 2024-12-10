import pytest
from httpx import AsyncClient
from fastapi import status

# Test data
test_user = {
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpassword123"
}

@pytest.mark.asyncio
async def test_register_user(async_client: AsyncClient):
    """Test user registration with valid data."""
    response = await async_client.post(
        "/auth/register",
        json=test_user
    )
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["message"] == "User registered successfully"
    assert data["username"] == test_user["username"]
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_user(async_client: AsyncClient):
    """Test user login with valid credentials."""
    # First register a user
    await async_client.post("/auth/register", json=test_user)
    
    # Then try to login
    login_data = {
        "username": test_user["username"],
        "password": test_user["password"]
    }
    response = await async_client.post("/auth/login", json=login_data)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_get_user_details(async_client: AsyncClient):
    """Test getting user details."""
    # First register a user
    register_response = await async_client.post(
        "/auth/register",
        json=test_user
    )
    token = register_response.json()["access_token"]
    
    # Get user details
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get(
        f"/auth/users/{test_user['username']}",
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["username"] == test_user["username"]

@pytest.mark.asyncio
async def test_change_password(async_client: AsyncClient):
    """Test password change functionality."""
    # First register a user
    register_response = await async_client.post(
        "/auth/register",
        json=test_user
    )
    token = register_response.json()["access_token"]
    
    # Change password
    headers = {"Authorization": f"Bearer {token}"}
    password_change_data = {
        "current_password": test_user["password"],
        "new_password": "newpassword123"
    }
    
    response = await async_client.put(
        f"/auth/users/{test_user['username']}/password",
        json=password_change_data,
        headers=headers
    )
    
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Password updated successfully"

@pytest.mark.asyncio
async def test_logout(async_client: AsyncClient):
    """Test logout endpoint."""
    response = await async_client.post("/auth/logout")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Successfully logged out"