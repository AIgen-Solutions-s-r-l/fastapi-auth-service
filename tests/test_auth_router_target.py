import uuid
import pytest
from httpx import AsyncClient
import json

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

# Test login with malformed credentials
async def test_login_malformed(client: AsyncClient):
    response = await client.post("/auth/login", json={
        "username": "",  # Empty username
        "password": "password"
    })
    assert response.status_code == 401, "Should handle malformed credentials"

# Test login with bad JSON
async def test_login_bad_json(client: AsyncClient):
    response = await client.post("/auth/login", content=b"not json")
    assert response.status_code in [400, 422], "Should reject bad JSON"

# Test registration validation
async def test_register_validation(client: AsyncClient):
    # Test with invalid email format
    response = await client.post("/auth/register", json={
        "username": "newuser",
        "email": "not_an_email",  # Invalid email
        "password": "Password123!"
    })
    assert response.status_code == 422, "Should reject invalid email format"
    
    # Test with short password
    response = await client.post("/auth/register", json={
        "username": "newuser", 
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
        f"/auth/users/{test_user['username']}/email",
        json={
            "new_email": "",  # Empty email
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 422, "Should reject empty email"
    
    # Test email change with no json
    response = await client.put(
        f"/auth/users/{test_user['username']}/email",
        content=b"not json",
        headers=headers
    )
    assert response.status_code in [400, 422], "Should reject invalid JSON"

# Test get user details with various edge cases
async def test_get_user_details_edges(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with username containing special chars
    response = await client.get("/auth/users/user%20with%20spaces", headers=headers)
    assert response.status_code in [404, 422], "Should handle special chars in username"

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
        f"/auth/users/{test_user['username']}/password",
        json={"current_password": "", "new_password": "NewPassword123!"},
        headers=headers
    )
    assert response.status_code in [401, 422], "Should reject empty current password"
    
    # Test with empty new password
    response = await client.put(
        f"/auth/users/{test_user['username']}/password",
        json={"current_password": test_user["password"], "new_password": ""},
        headers=headers
    )
    assert response.status_code in [400, 422], "Should reject empty new password"

# Test user deletion with empty password
async def test_remove_user_empty_password(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Test with empty password
    response = await client.delete(
        f"/auth/users/{test_user['username']}",
        params={"password": ""},
        headers=headers
    )
    assert response.status_code in [401, 422], "Should reject empty password"

# Test creating multiple users to check registration edge cases
async def test_multiple_registrations(client: AsyncClient):
    # Create first user
    username1 = f"multi_user1_{uuid.uuid4().hex[:8]}"
    email1 = f"{username1}@example.com"
    password1 = "TestPassword123!"
    
    response1 = await client.post("/auth/register", json={
        "username": username1,
        "email": email1,
        "password": password1
    })
    assert response1.status_code == 201
    data1 = response1.json()
    token1 = data1.get("access_token")
    
    # Try to create another user with same username
    response2 = await client.post("/auth/register", json={
        "username": username1,  # Same username
        "email": f"different_{uuid.uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!"
    })
    assert response2.status_code in [400, 409], "Should reject duplicate username"
    
    # Try to create another user with same email
    response3 = await client.post("/auth/register", json={
        "username": f"different_{uuid.uuid4().hex[:8]}",
        "email": email1,  # Same email
        "password": "TestPassword123!"
    })
    assert response3.status_code in [400, 409], "Should reject duplicate email"
    
    # Cleanup
    headers = {"Authorization": f"Bearer {token1}"}
    await client.delete(f"/auth/users/{username1}", params={"password": password1}, headers=headers)

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
    response2 = await client.get(f"/auth/users/{test_user['username']}", headers=headers)
    assert response2.status_code == 200
    
    # Try to access with missing token
    response3 = await client.get("/auth/me")
    assert response3.status_code == 401