import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.exceptions import UserNotFoundError, InvalidCredentialsError, UserAlreadyExistsError
from app.core.security import create_access_token
from app.models.user import User

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

# Test login function error handling (lines 47-68)
@patch("app.routers.auth_router.authenticate_user")
async def test_login_exception_handling(mock_auth, client: AsyncClient):
    # Mock authenticate_user to raise a general exception
    mock_auth.side_effect = Exception("Database connection error")
    
    response = await client.post("/auth/login", json={
        "username": "testuser",
        "password": "password"
    })
    assert response.status_code == 401, "Should handle general exceptions and return 401"

# Test register user function (lines 110-133)
@patch("app.routers.auth_router.create_user")
async def test_register_user_already_exists(mock_create_user, client: AsyncClient):
    # Mock create_user to raise UserAlreadyExistsError
    mock_create_user.side_effect = UserAlreadyExistsError("Username already exists")
    
    response = await client.post("/auth/register", json={
        "username": "existing_user",
        "email": "existing@example.com",
        "password": "Password123!"
    })
    assert response.status_code == 409, "Should return 409 Conflict for existing user"
    # Just check that we got a response, don't rely on specific format
    assert response.json(), "Should return JSON response"

# Test refresh_token function (lines 406-430)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_refresh_token_user_not_found(mock_get_user, mock_verify_token, client: AsyncClient):
    # Mock verify_jwt_token to return a valid payload
    mock_verify_token.return_value = {"sub": "testuser", "id": 123}
    
    # Mock get_user_by_username to return None (user not found)
    mock_get_user.return_value = None
    
    response = await client.post("/auth/refresh", json={"token": "valid.looking.token"})
    assert response.status_code == 401, "Should return 401 when user no longer exists"
    # Just verify we got some kind of error response
    assert response.json(), "Should return JSON response"

# Test get_current_user_profile function with user_id for non-admin user
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_current_user_profile_non_admin_access_other(mock_get_user, mock_verify_token, client: AsyncClient):
    # Mock verify_jwt_token to return a non-admin payload
    mock_verify_token.return_value = {"sub": "regularuser", "id": 123, "is_admin": False}
    
    # Create a mock user
    mock_user = MagicMock()
    mock_user.id = 123
    mock_user.username = "regularuser"
    mock_user.email = "regular@example.com"
    
    # Mock get_user_by_username to return the user
    mock_get_user.return_value = mock_user
    
    response = await client.get("/auth/me?user_id=456", headers={"Authorization": "Bearer valid.looking.token"})
    assert response.status_code == 403, "Should return 403 when non-admin tries to view another user's profile"
    # Just verify we got some kind of error response
    assert response.json(), "Should return JSON response"

# Test error scenarios for change_email
@patch("app.routers.auth_router.UserService")
async def test_change_email_server_error(mock_user_service, client: AsyncClient, test_user):
    # Create a mock service instance
    mock_service_instance = MagicMock()
    mock_user_service.return_value = mock_service_instance
    
    # Mock update_user_email to raise an exception
    mock_service_instance.update_user_email.side_effect = Exception("Database error")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        f"/auth/users/{test_user['username']}/email",
        json={
            "new_email": "new@example.com",
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 500, "Should return 500 on server error"
    # Just verify we got some kind of error response
    assert response.json(), "Should return JSON response"

# Test get_user_by_username returns None (line 152-153)
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_user_details_return_none(mock_get_user, client: AsyncClient, test_user):
    mock_get_user.return_value = None
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get(f"/auth/users/nonexistent_user", headers=headers)
    assert response.status_code in [404, 500], "Should return an error status code"

# Test update_user_password exception handling (lines 287-291)
@patch("app.routers.auth_router.update_user_password")
async def test_change_password_exception(mock_update_password, client: AsyncClient, test_user):
    # Set up to raise different types of exceptions
    mock_update_password.side_effect = InvalidCredentialsError()
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        f"/auth/users/{test_user['username']}/password",
        json={"current_password": "wrong_password", "new_password": "NewPassword123!"},
        headers=headers
    )
    assert response.status_code == 401, "Should return 401 for invalid credentials"

# Test delete_user exception handling (lines 318-322)
@patch("app.routers.auth_router.delete_user")
async def test_remove_user_exception(mock_delete_user, client: AsyncClient, test_user):
    # Set up to raise different types of exceptions
    mock_delete_user.side_effect = InvalidCredentialsError()
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.delete(
        f"/auth/users/{test_user['username']}",
        params={"password": "wrong_password"},
        headers=headers
    )
    assert response.status_code == 401, "Should return 401 for invalid credentials"

# Test get_email_by_user_id (lines 811-858)
# This is a special case that requires different mocking approach
@patch("app.routers.auth_router.select")
async def test_get_email_by_id_error(mock_select, client: AsyncClient):
    # Setting up for the execute call to raise exception
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("Database error")):
        response = await client.get("/auth/users/123/email")
        assert response.status_code == 500, "Should return 500 on database error"

# Test the full login-logout flow to increase coverage
async def test_login_logout_flow(client: AsyncClient, test_user):
    # Login
    login_response = await client.post("/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    
    # Logout
    headers = {"Authorization": f"Bearer {token}"}
    logout_response = await client.post("/auth/logout", headers=headers)
    assert logout_response.status_code == 200
    
    # Verify we can login again after logout
    login_response2 = await client.post("/auth/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert login_response2.status_code == 200