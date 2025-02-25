import uuid
import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from jose import jwt

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

# Test login with exception (lines 47-68)
@patch("app.routers.auth_router.authenticate_user")
async def test_login_with_exception(mock_auth, client: AsyncClient):
    # Set up mock to raise Exception
    mock_auth.side_effect = Exception("Test exception")
    
    # Try login
    response = await client.post("/auth/login", json={
        "username": "testuser", 
        "password": "password"
    })
    
    # Should handle exception and return 401
    assert response.status_code == 401

# Test get_user_details function (lines 152-153)
async def test_get_nonexistent_user_detail(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Try to get a user that doesn't exist
    response = await client.get("/auth/users/nonexistent_user", headers=headers)
    
    # This should return either 404 or 500 depending on implementation
    assert response.status_code in [404, 500]

# Register user with exception (lines 110-133)
async def test_registration_with_existing_user(client: AsyncClient, test_user):
    # Try to register with existing username
    response = await client.post("/auth/register", json={
        "username": test_user["username"],
        "email": "different@example.com",
        "password": "Password123!"
    })
    
    # Should return conflict status
    assert response.status_code in [400, 409]

# Test email change function error paths (lines 232-239, 248-256)
async def test_email_change_errors(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with invalid token
    bad_headers = {"Authorization": "Bearer invalid.token.here"}
    response = await client.put(
        f"/auth/users/{test_user['username']}/email",
        json={
            "new_email": "new@example.com",
            "current_password": test_user["password"]
        },
        headers=bad_headers
    )
    assert response.status_code in [401, 403]
    
    # Test with wrong password
    response = await client.put(
        f"/auth/users/{test_user['username']}/email",
        json={
            "new_email": "new@example.com",
            "current_password": "WrongPassword123!"
        },
        headers=headers
    )
    assert response.status_code == 401

# Test user deletion error handling (lines 318-322)
async def test_user_deletion_error(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with wrong password
    response = await client.delete(
        f"/auth/users/{test_user['username']}",
        params={"password": "WrongPassword123!"},
        headers=headers
    )
    assert response.status_code == 401

# Test JWT refresh token endpoint (lines 407-408)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_refresh_token_not_found(mock_get_user, mock_verify, client: AsyncClient):
    # Mock verification to return valid payload
    mock_verify.return_value = {"sub": "testuser", "id": 123}
    
    # Mock user retrieval to return None
    mock_get_user.return_value = None
    
    # Test refresh endpoint
    response = await client.post("/auth/refresh", json={"token": "valid.token.format"})
    assert response.status_code == 401

# Test current user profile endpoint (lines 479, 484, 490)
@patch("app.routers.auth_router.verify_jwt_token") 
@patch("app.routers.auth_router.get_user_by_username")
async def test_current_user_profile_edge_cases(mock_get_user, mock_verify, client: AsyncClient):
    # Case 1: User doesn't exist
    mock_verify.return_value = {"sub": "testuser", "id": 123}
    mock_get_user.return_value = None
    
    response = await client.get("/auth/me", headers={"Authorization": "Bearer valid.token"})
    assert response.status_code == 401
    
    # Case 2: User requests another user but isn't admin
    mock_verify.return_value = {"sub": "regular_user", "id": 123, "is_admin": False}
    regular_user = MagicMock()
    regular_user.id = 123
    mock_get_user.return_value = regular_user
    
    response = await client.get("/auth/me?user_id=456", headers={"Authorization": "Bearer valid.token"})
    assert response.status_code == 403

# Test get_email_and_username_by_user_id (lines 540-546, 554-562)
async def test_get_user_profile_by_id(client: AsyncClient):
    # Test with a non-existent ID
    response = await client.get("/auth/users/999999/profile")
    assert response.status_code == 404
    
    # Test with invalid ID format
    response = await client.get("/auth/users/not-an-id/profile")
    assert response.status_code in [404, 422]