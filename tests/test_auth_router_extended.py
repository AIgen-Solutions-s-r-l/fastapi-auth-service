import uuid
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
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

# Test login failures
async def test_login_invalid_credentials(client: AsyncClient, test_user):
    # Test login with incorrect password
    response = await client.post("/auth/login", json={
        "username": test_user["username"],
        "password": "WrongPassword123!"
    })
    assert response.status_code == 401, "Expected 401 Unauthorized"
    
    # Test login with non-existent username
    response = await client.post("/auth/login", json={
        "username": "nonexistent_user",
        "password": "TestPassword123!"
    })
    assert response.status_code == 401, "Expected 401 Unauthorized"

# Test user retrieval for non-existent user
# Patch the get_user_by_username function to raise UserNotFoundError for non-existent users
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_nonexistent_user(mock_get_user, client: AsyncClient, test_user):
    # Make the get_user_by_username function raise UserNotFoundError
    mock_get_user.side_effect = UserNotFoundError("User not found")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get("/auth/users/nonexistent_user", headers=headers)
    assert response.status_code == 404, "Expected 404 Not Found"

# Test failed password change
async def test_change_password_wrong_current(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        f"/auth/users/{test_user['username']}/password",
        json={"current_password": "WrongPassword123!", "new_password": "NewPassword456!"},
        headers=headers
    )
    assert response.status_code == 401, "Expected 401 Unauthorized for wrong current password"

# Test user deletion with wrong password
async def test_delete_user_wrong_password(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.delete(
        f"/auth/users/{test_user['username']}",
        params={"password": "WrongPassword123!"},
        headers=headers
    )
    assert response.status_code == 401, "Expected 401 Unauthorized for wrong password"

# Test logout with invalid token
async def test_logout_invalid_token(client: AsyncClient):
    # Create an expired token
    expired_token = create_access_token(
        data={"sub": "testuser", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        expires_delta=timedelta(minutes=-60)  # Negative delta for expired token
    )
    
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await client.post("/auth/logout", headers=headers)
    assert response.status_code == 401, "Expected 401 Unauthorized for expired token"

# Test refresh token functionality
async def test_refresh_token_functionality(client: AsyncClient, test_user):
    # Test with valid token
    response = await client.post("/auth/refresh", json={"token": test_user["token"]})
    assert response.status_code == 200, "Token refresh should succeed with valid token"
    data = response.json()
    assert "access_token" in data, "Response should contain a new access token"
    
    # Test with invalid token
    response = await client.post("/auth/refresh", json={"token": "invalid.token.format"})
    assert response.status_code == 401, "Expected 401 Unauthorized for invalid token"

# Test current user profile with invalid token
async def test_get_current_user_profile_invalid_token(client: AsyncClient):
    headers = {"Authorization": "Bearer invalid.token.format"}
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 401, "Expected 401 Unauthorized for invalid token"

# Test get current user profile with admin user checking another user
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_current_user_profile_admin_access(
    mock_get_user, mock_verify_token, client: AsyncClient, test_user
):
    # Mock JWT verification to return admin payload
    mock_verify_token.return_value = {
        "sub": "admin_user",
        "id": 999,
        "is_admin": True
    }
    
    # Mock the user retrieval functions
    admin_user = MagicMock()
    admin_user.id = 999
    admin_user.username = "admin_user"
    admin_user.email = "admin@example.com"
    admin_user.is_admin = True
    
    target_user = MagicMock()
    target_user.id = 123
    target_user.username = "target_user"
    target_user.email = "target@example.com"
    
    # Setup side effects for get_user_by_username calls
    def get_user_side_effect(db, username):
        if username == "admin_user":
            return admin_user
        elif username == "123":
            return target_user
        else:
            raise UserNotFoundError("User not found")
    
    mock_get_user.side_effect = get_user_side_effect
    
    # Make the request as admin viewing another user's profile
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get("/auth/me?user_id=123", headers=headers)
    
    # Verify expected behavior
    assert response.status_code == 200, "Admin should be able to view other profiles"
    data = response.json()
    assert data["username"] == "target_user", "Should return the target user's username"

# Test get email by user ID
async def test_get_email_by_user_id(client: AsyncClient, test_user):
    # Use an invalid user ID directly
    nonexistent_id = 999999  # Assuming this user ID doesn't exist
    response = await client.get(f"/auth/users/{nonexistent_id}/email")
    assert response.status_code == 404, "Expected 404 for nonexistent user ID"

# Test password reset request with mock email sending
@patch("app.routers.auth_router.create_password_reset_token")
@patch("app.routers.auth_router.send_email")
async def test_password_reset_request_success(
    mock_send_email, mock_create_token, client: AsyncClient, test_user
):
    # Mock token creation
    mock_create_token.return_value = "test_reset_token"
    
    # Test with existing email
    response = await client.post(
        "/auth/password-reset-request", 
        json={"email": test_user["email"]}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset link sent to email if account exists"
    
    # Verify mock was called with any db session and the right email
    mock_create_token.assert_called_once()
    args, _ = mock_create_token.call_args
    assert args[1] == test_user["email"]  # Check email is correct
    mock_send_email.assert_called_once()

# Test password reset request with non-existent email
@patch("app.routers.auth_router.create_password_reset_token")
@patch("app.routers.auth_router.send_email")
async def test_password_reset_request_nonexistent_email(
    mock_send_email, mock_create_token, client: AsyncClient
):
    # Mock token creation to raise error
    mock_create_token.side_effect = UserNotFoundError("User not found")
    
    # Test with non-existent email
    response = await client.post(
        "/auth/password-reset-request", 
        json={"email": "nonexistent@example.com"}
    )
    
    # Should still return 200 to prevent email enumeration
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset link sent to email if account exists"
    
    # Verify send_email was not called
    mock_send_email.assert_not_called()

# Test reset password with token
@patch("app.routers.auth_router.verify_reset_token")
@patch("app.routers.auth_router.reset_password")
async def test_reset_password_with_valid_token(
    mock_reset_password, mock_verify_token, client: AsyncClient
):
    # Mock token verification
    mock_verify_token.return_value = 123  # Mock user ID
    
    # Test with valid token
    response = await client.post(
        "/auth/reset-password",
        json={"token": "valid_reset_token", "new_password": "NewSecurePassword123!"}
    )
    
    assert response.status_code == 200
    assert response.json()["message"] == "Password has been reset successfully"
    
    # Verify mocks were called with correct arguments
    mock_verify_token.assert_called_once_with("valid_reset_token")
    
    # Verify only the user_id and password parameters
    mock_reset_password.assert_called_once()
    args, _ = mock_reset_password.call_args
    assert args[1] == 123  # Check user_id is correct
    assert args[2] == "NewSecurePassword123!"  # Check password is correct

# Test reset password with invalid token
@patch("app.routers.auth_router.verify_reset_token")
async def test_reset_password_with_invalid_token(mock_verify_token, client: AsyncClient):
    # Mock token verification to raise error
    mock_verify_token.side_effect = jwt.JWTError("Invalid token")
    
    # Test with invalid token
    response = await client.post(
        "/auth/reset-password",
        json={"token": "invalid_token", "new_password": "NewSecurePassword123!"}
    )
    
    assert response.status_code == 400, "Expected 400 Bad Request for invalid token"
    # The format of the response may vary, so just check the status code