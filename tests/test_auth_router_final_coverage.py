import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

from app.core.exceptions import UserNotFoundError
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(async_client: AsyncClient):
    return async_client

@pytest.fixture
async def test_user(client: AsyncClient):
    # Generate a unique username and email
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"
    
    # Register the user
    response = await client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    if response.status_code != 201:
        pytest.skip("Registration failed, skipping auth router tests")
    data = response.json()
    token = data.get("access_token")
    user_data = {"username": username, "email": email, "password": password, "token": token}
    
    yield user_data
    
    # Cleanup: delete the user after tests run
    await client.delete(f"/auth/users/{username}",
                       params={"password": password},
                       headers={"Authorization": f"Bearer {token}"})

# Test user not found explicitly raising UserNotFoundError
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_user_details_raises_error(mock_get_user, client: AsyncClient, test_user):
    # Mock to raise UserNotFoundError with required identifier parameter
    mock_get_user.side_effect = UserNotFoundError("nonexistent_user")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get("/auth/users/nonexistent_user", headers=headers)
    assert response.status_code == 404

# Test the exception cases of change_password with a custom exception
@patch("app.routers.auth_router.update_user_password")
async def test_change_password_error(mock_update, client: AsyncClient, test_user):
    # Create a custom exception that matches the signature
    class CustomError(Exception):
        pass
    
    mock_update.side_effect = CustomError("Invalid password")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        f"/auth/users/{test_user['username']}/password",
        json={"current_password": "wrong", "new_password": "NewPassword123!"},
        headers=headers
    )
    assert response.status_code in [401, 500]

# Test the exception cases of remove_user with a custom exception
@patch("app.routers.auth_router.delete_user")
async def test_remove_user_error(mock_delete, client: AsyncClient, test_user):
    # Create a custom exception that matches the signature
    class CustomError(Exception):
        pass
    
    mock_delete.side_effect = CustomError("Invalid password")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.delete(
        f"/auth/users/{test_user['username']}",
        params={"password": "wrong_password"},
        headers=headers
    )
    assert response.status_code in [401, 500]

# Test the refresh token flow with mocked user
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_refresh_token_mock_full_flow(mock_get_user, mock_verify, client: AsyncClient):
    # Mock the token verification
    mock_verify.return_value = {
        "sub": "test_user",
        "id": 123,
        "is_admin": False,
        "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
    }
    
    # Create a mock user
    mock_user = MagicMock()
    mock_user.username = "test_user"
    mock_user.id = 123
    mock_user.is_admin = False
    mock_user.email = "test@example.com"
    
    # Set up the mock to return our user
    mock_get_user.return_value = mock_user
    
    # Test the refresh endpoint
    response = await client.post("/auth/refresh", json={"token": "valid.token.here"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

# Test the email update function with a complete mock
@patch("app.routers.auth_router.UserService")
@patch("app.routers.auth_router.verify_jwt_token")
async def test_change_email_complete_mock(mock_verify, mock_service, client: AsyncClient):
    # Mock JWT verification
    mock_verify.return_value = {
        "sub": "test_user",
        "id": 123,
        "is_admin": False
    }
    
    # Create a mock user
    mock_user = MagicMock()
    mock_user.username = "test_user"
    mock_user.email = "updated@example.com"
    
    # Create a mock service instance with AsyncMock for async methods
    mock_instance = MagicMock()
    mock_service.return_value = mock_instance
    mock_instance.update_user_email = AsyncMock(return_value=mock_user)
    
    # Test the endpoint
    response = await client.put(
        "/auth/users/test_user/email",
        json={"new_email": "updated@example.com", "current_password": "Password123!"},
        headers={"Authorization": "Bearer token"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "updated@example.com"
    assert "message" in data

# Test get_current_user_profile with admin checking non-existent user
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_profile_admin_nonexistent_user(mock_get_user, mock_verify, client: AsyncClient):
    # Mock JWT verification for admin
    mock_verify.return_value = {
        "sub": "admin_user",
        "id": 999,
        "is_admin": True
    }
    
    # Create a mock admin user
    admin_user = MagicMock()
    admin_user.id = 999
    admin_user.username = "admin_user"
    admin_user.email = "admin@example.com"
    
    # Set up mock to return admin for first call, but raise UserNotFoundError for second call
    def side_effect(db, username):
        if username == "admin_user":
            return admin_user
        raise UserNotFoundError("Requested user not found")
    
    mock_get_user.side_effect = side_effect
    
    # Test the endpoint
    response = await client.get(
        "/auth/me?user_id=456",
        headers={"Authorization": "Bearer admin_token"}
    )
    
    assert response.status_code == 404

# Comprehensive test for register endpoint
async def test_register_comprehensive(client: AsyncClient):
    # Generate unique user data
    username = f"comp_user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "StrongP@ssw0rd!"
    
    # Register the user
    response = await client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == username
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "message" in data
    
    # Cleanup - delete the user
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    await client.delete(
        f"/auth/users/{username}",
        params={"password": password},
        headers=headers
    )

# Test handling of profile retrieval by user ID
@patch("app.routers.auth_router.select")
async def test_get_user_profile_by_id_mocked(mock_select, client: AsyncClient):
    # Create a mock user result for the select query
    mock_user = MagicMock()
    mock_user.email = "user123@example.com"
    mock_user.username = "user123"
    
    # Create a mock for the result of db.execute
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    
    # Set up db.execute to be properly mocked within the context of where it's used
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", return_value=mock_result):
        response = await client.get("/auth/users/123/profile")
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "user123@example.com"
        assert data["username"] == "user123"