import uuid
import pytest
from httpx import AsyncClient
import json

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(async_client: AsyncClient):
    return async_client

# Use the shared test_user fixture from conftest.py that performs login to get token

# Test login with malformed credentials
async def test_login_malformed(client: AsyncClient):
    response = await client.post("/auth/login", json={
        "email": "",  # Empty email
        "password": "password"
    })
    assert response.status_code in [401, 422], "Should handle malformed credentials"

# Test login with bad JSON
async def test_login_bad_json(client: AsyncClient):
    response = await client.post("/auth/login", content=b"not json")
    assert response.status_code in [400, 422], "Should reject bad JSON"

# Test registration validation
async def test_register_validation(client: AsyncClient):
    # Test with invalid email format
    response = await client.post("/auth/register", json={
        "email": "not_an_email",  # Invalid email
        "password": "Password123!"
    })
    assert response.status_code == 422, "Should reject invalid email format"
    
    # Test with short password
    response = await client.post("/auth/register", json={
        "email": "valid@example.com",
        "password": "short"  # Too short password
    })
    assert response.status_code == 422, "Should reject short password"

# Test refresh token endpoint more thoroughly
async def test_refresh_token_invalid(client: AsyncClient):
    # Test with invalid token format
    response = await client.post("/auth/refresh", json={
        "token": "not.a.token"
    })
    assert response.status_code == 401, "Should reject invalid token format"
    
    # Test with empty token
    response = await client.post("/auth/refresh", json={
        "token": ""
    })
    assert response.status_code in [401, 422], "Should reject empty token"

# Test email change with comprehensive coverage
async def test_change_email_comprehensive(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test email change with empty email
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": "",  # Empty email
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 422, "Should reject empty email"
    
    # Test email change with no json
    response = await client.put(
        "/auth/users/change-email",
        content=b"not json",
        headers=headers
    )
    assert response.status_code in [400, 422], "Should reject invalid JSON"

# Test get user details with various edge cases
async def test_get_user_details_edges(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with email containing special chars
    response = await client.get("/auth/users/by-email/user%20with%20spaces%40example.com", headers=headers)
    assert response.status_code in [404, 422], "Should handle special chars in email"

# Test get user profile by non-existent ID
async def test_get_user_profile_nonexistent(client: AsyncClient):
    # Use a very large number (unlikely to exist)
    response = await client.get("/auth/users/99999999/profile")
    assert response.status_code == 404, "Should return 404 for non-existent user ID"

# Test change password with empty passwords
async def test_change_password_edges(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with empty current password
    response = await client.put(
        "/auth/users/change-password",
        json={"current_password": "", "new_password": "NewPassword123!"},
        headers=headers
    )
    assert response.status_code in [401, 422], "Should reject empty current password"
    
    # Test with empty new password
    response = await client.put(
        "/auth/users/change-password",
        json={"current_password": test_user["password"], "new_password": ""},
        headers=headers
    )
    assert response.status_code in [400, 422], "Should reject empty new password"

# Test user deletion with empty password
async def test_remove_user_empty_password(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with empty password
    response = await client.delete(
        "/auth/users/delete-account",
        params={"password": ""},
        headers=headers
    )
    assert response.status_code in [401, 422], "Should reject empty password"

# Test creating multiple users to check registration edge cases
async def test_multiple_registrations(client: AsyncClient):
    # Create first user with random email
    email1 = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password1 = "TestPassword123!"
    
    response1 = await client.post("/auth/register", json={
        "email": email1,
        "password": password1
    })
    assert response1.status_code == 201
    
    # Login to get token
    login_response = await client.post("/auth/login", json={
        "email": email1,
        "password": password1
    })
    assert login_response.status_code == 200
    login_data = login_response.json()
    token1 = login_data.get("access_token")
    
    # Try to create another user with same email
    response2 = await client.post("/auth/register", json={
        "email": email1,  # Same email
        "password": "TestPassword123!"
    })
    assert response2.status_code in [400, 409], "Should reject duplicate email"
    
    # Cleanup
    headers = {"Authorization": f"Bearer {token1}"}
    await client.delete("/auth/users/delete-account", params={"password": password1}, headers=headers)

# Test logout with various token issues
async def test_logout_edge_cases(client: AsyncClient, test_user):
    # Test with malformed token
    headers = {"Authorization": "Bearer malformed.token.here"}
    response = await client.post("/auth/logout", headers=headers)
    assert response.status_code == 401, "Should reject malformed token"
    
    # Test with no token
    response = await client.post("/auth/logout")
    assert response.status_code == 401, "Should require token"

# Test all user profile endpoints together for coverage
async def test_user_profile_flow(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Get current user profile
    response1 = await client.get("/auth/me", headers=headers)
    assert response1.status_code == 200
    
    # Get user profile by username
    response2 = await client.get(f"/auth/users/by-email/{test_user['email']}", headers=headers)
    assert response2.status_code == 200
    
    # Try to access with missing token
    response3 = await client.get("/auth/me")
    assert response3.status_code == 401