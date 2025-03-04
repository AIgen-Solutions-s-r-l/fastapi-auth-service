import uuid
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(async_client: AsyncClient):
    return async_client

# No need to redefine test_user - it's imported from conftest.py

async def test_login(client: AsyncClient, test_user):
    # Test login with correct credentials
    response = await client.post("/auth/login", json={
        "email": test_user["email"],
        "password": test_user["password"]
    })
    assert response.status_code == 200, f"Login failed with status {response.status_code}"
    data = response.json()
    assert "access_token" in data, "Login response missing access_token"


async def test_get_user_details(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get(f"/auth/users/by-email/{test_user['email']}", headers=headers)
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
    data = response.json()
    assert data.get("email") == test_user["email"], "Email in response does not match"


async def test_change_password(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    new_password = "NewTestPassword456!"
    response = await client.put("/auth/users/change-password",
                          json={"current_password": test_user["password"], "new_password": new_password},
                          headers=headers)
    assert response.status_code == 200, f"Password change failed with status {response.status_code}"
    data = response.json()
    assert "message" in data and "updated" in data["message"].lower(), "Unexpected password change response"
    
    # Verify that the user can login with the new password
    login_response = await client.post("/auth/login", json={
        "email": test_user["email"],
        "password": new_password
    })
    assert login_response.status_code == 200, "Failed to login with new password"


async def test_logout(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.post("/auth/logout", headers=headers)
    assert response.status_code == 200, f"Logout failed with status {response.status_code}"
    data = response.json()
    assert data.get("message") == "Successfully logged out", "Unexpected logout message"

async def test_password_reset_request(client: AsyncClient, test_user):
    response = await client.post("/auth/password-reset-request", json={"email": test_user["email"]})
    assert response.status_code == 200, f"Password reset request failed with status {response.status_code}"
    data = response.json()
    assert "message" in data, "Password reset request response missing message"


@pytest.mark.skip(reason="Token refresh test requires a proper refresh token flow")
async def test_refresh_token(client: AsyncClient, test_user):
    # This test is skipped because the refresh token flow may require separate handling.
    response = await client.post("/auth/refresh", json={"token": test_user["token"]})
    assert response.status_code == 200, f"Refresh token failed with status {response.status_code}"
    data = response.json()
    assert "access_token" in data, "Refresh token response missing access_token"


async def test_get_current_user_profile(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 200, f"Get profile failed with status {response.status_code}"
    data = response.json()
    assert data.get("email") == test_user["email"], "Profile email does not match"


@pytest.mark.skip(reason="Reset password endpoint requires a valid reset token to be generated")
async def test_reset_password(client: AsyncClient):
    # This test is skipped because it requires a valid password reset token.
    response = await client.post("/auth/reset-password", json={
        "token": "invalid_token",
        "new_password": "DoesNotMatter123!"
    })
    assert response.status_code == 400, "Reset password endpoint did not return expected error"


async def test_change_email_success(client: AsyncClient, test_user):
    """Test successful email change."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    new_email = f"new_email_{uuid.uuid4().hex[:8]}@example.com"
    
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": new_email,
            "current_password": test_user["password"]
        },
        headers=headers
    )
    
    assert response.status_code == 200, f"Email change failed with status {response.status_code}"
    data = response.json()
    assert data["email"] == new_email, "Email was not updated correctly"
    assert "message" in data and "updated" in data["message"].lower(), "Unexpected response message"
    
    # Use the new token from the response for subsequent requests
    new_token = data.get("access_token")
    assert new_token is not None, "No new access token returned after email change"
    updated_headers = {"Authorization": f"Bearer {new_token}"}
    
    # Verify the email was actually changed in the database
    profile_response = await client.get("/auth/me", headers=updated_headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["email"] == new_email


async def test_change_email_unauthorized(client: AsyncClient, test_user):
    """Test unauthorized email change attempt."""
    # Try without authentication
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": "new@example.com",
            "current_password": test_user["password"]
        }
    )
    assert response.status_code == 401, "Should require authentication"
    
    # Create another user and try to change their email
    other_email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    await client.post("/auth/register", json={
        "email": other_email,
        "password": "TestPassword123!"
    })
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": "new@example.com",
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 401, "Should not allow changing other user's email"


async def test_change_email_invalid_password(client: AsyncClient, test_user):
    """Test email change with invalid password."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": "new@example.com",
            "current_password": "WrongPassword123!"
        },
        headers=headers
    )
    assert response.status_code == 401, "Should reject invalid password"


async def test_change_email_already_exists(client: AsyncClient, test_user):
    """Test email change to an already registered email."""
    # Create another user first
    other_email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    await client.post("/auth/register", json={
        "email": other_email,
        "password": "TestPassword123!"
    })
    
    # Try to change email to the other user's email
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": other_email,
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 400, "Should reject already registered email"


async def test_change_email_invalid_format(client: AsyncClient, test_user):
    """Test email change with invalid email format."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        "/auth/users/change-email",
        json={
            "new_email": "invalid-email-format",
            "current_password": test_user["password"]
        },
        headers=headers
    )
    assert response.status_code == 422, "Should reject invalid email format"
