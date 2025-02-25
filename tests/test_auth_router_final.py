import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

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
    
    # More flexible assertion to handle different response formats
    response_json = response.json()
    assert any("already exists" in str(val) for val in response_json.values()), "Response should indicate user exists"

# Test get_email_and_username_by_user_id function (lines 538-562)
@patch("sqlalchemy.ext.asyncio.AsyncSession.execute")
async def test_get_email_and_username_by_user_id_found(mock_execute, client: AsyncClient):
    # Create a mock user to return
    mock_user = MagicMock()
    mock_user.email = "test@example.com"
    mock_user.username = "testuser"
    
    # Mock the database query result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_execute.return_value = mock_result
    
    response = await client.get("/auth/users/123/profile")
    assert response.status_code == 200, "Should return 200 when user is found"
    data = response.json()
    assert data["email"] == "test@example.com", "Should return user's email"
    assert data["username"] == "testuser", "Should return user's username"

@patch("sqlalchemy.ext.asyncio.AsyncSession.execute")
async def test_get_email_and_username_by_user_id_not_found(mock_execute, client: AsyncClient):
    # Mock the database query result - user not found
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_execute.return_value = mock_result
    
    response = await client.get("/auth/users/999/profile")
    assert response.status_code == 404, "Should return 404 when user is not found"
    # More flexible check for the error message
    response_json = response.json()
    assert any("not found" in str(val).lower() for val in response_json.values()), "Response should indicate user not found"

@patch("sqlalchemy.ext.asyncio.AsyncSession.execute")
async def test_get_email_and_username_by_user_id_exception(mock_execute, client: AsyncClient):
    # Mock the database query to raise an exception
    mock_execute.side_effect = Exception("Database error")
    
    response = await client.get("/auth/users/123/profile")
    assert response.status_code == 500, "Should return 500 on database error"

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
    
    # More flexible assertion for the error message
    response_json = response.json()
    assert any("invalid" in str(val).lower() for val in response_json.values()), "Response should indicate invalid token"

# Test get_current_user_profile function (lines 479, 484, 490)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_current_user_profile_user_not_found(mock_get_user, mock_verify_token, client: AsyncClient):
    # Mock verify_jwt_token to return a valid payload
    mock_verify_token.return_value = {"sub": "testuser", "id": 123}
    
    # Mock get_user_by_username to return None (user not found)
    mock_get_user.return_value = None
    
    response = await client.get("/auth/me", headers={"Authorization": "Bearer valid.looking.token"})
    assert response.status_code == 401, "Should return 401 when user no longer exists"

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
    
    # More flexible assertion for the error message
    response_json = response.json()
    assert any("not authorized" in str(val).lower() for val in response_json.values()), "Response should indicate unauthorized access"

# Test error scenarios for change_email, change_password, and remove_user functions
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
    
    # More flexible assertion for the error message
    response_json = response.json()
    assert any("error" in str(val).lower() for val in response_json.values()), "Response should indicate email update error"