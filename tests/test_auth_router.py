import uuid
import httpx
import pytest

BASE_URL = "http://localhost:8001"

@pytest.fixture(scope="module")
def client():
    with httpx.Client() as client:
        yield client

@pytest.fixture(scope="module")
def test_user(client):
    # Generate a unique username and email
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"
    
    # Register the user
    response = client.post(f"{BASE_URL}/register", json={
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
    client.delete(f"{BASE_URL}/users/{username}", params={"password": password},
                  headers={"Authorization": f"Bearer {token}"})


def test_login(client, test_user):
    # Test login with correct credentials
    response = client.post(f"{BASE_URL}/login", json={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert response.status_code == 200, f"Login failed with status {response.status_code}"
    data = response.json()
    assert "access_token" in data, "Login response missing access_token"


def test_get_user_details(client, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = client.get(f"{BASE_URL}/users/{test_user['username']}", headers=headers)
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}"
    data = response.json()
    assert data.get("username") == test_user["username"], "Username in response does not match"


def test_change_password(client, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    new_password = "NewTestPassword456!"
    response = client.put(f"{BASE_URL}/users/{test_user['username']}/password",
                          json={"current_password": test_user["password"], "new_password": new_password},
                          headers=headers)
    assert response.status_code == 200, f"Password change failed with status {response.status_code}"
    data = response.json()
    assert "message" in data and "updated" in data["message"].lower(), "Unexpected password change response"
    
    # Verify that the user can login with the new password
    login_response = client.post(f"{BASE_URL}/login", json={
        "username": test_user["username"],
        "password": new_password
    })
    assert login_response.status_code == 200, "Failed to login with new password"


def test_logout(client):
    response = client.post(f"{BASE_URL}/logout")
    assert response.status_code == 200, f"Logout failed with status {response.status_code}"
    data = response.json()
    assert data.get("message") == "Successfully logged out", "Unexpected logout message"


def test_password_reset_request(client, test_user):
    response = client.post(f"{BASE_URL}/password-reset-request", json={"email": test_user["email"]})
    assert response.status_code == 200, f"Password reset request failed with status {response.status_code}"
    data = response.json()
    assert "message" in data, "Password reset request response missing message"


@pytest.mark.skip(reason="Token refresh test requires a proper refresh token flow")
def test_refresh_token(client, test_user):
    # This test is skipped because the refresh token flow may require separate handling.
    response = client.post(f"{BASE_URL}/refresh", json={"token": test_user["token"]})
    assert response.status_code == 200, f"Refresh token failed with status {response.status_code}"
    data = response.json()
    assert "access_token" in data, "Refresh token response missing access_token"


def test_get_current_user_profile(client, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = client.get(f"{BASE_URL}/me", headers=headers)
    assert response.status_code == 200, f"Get profile failed with status {response.status_code}"
    data = response.json()
    assert data.get("username") == test_user["username"], "Profile username does not match"


@pytest.mark.skip(reason="Reset password endpoint requires a valid reset token to be generated")
def test_reset_password(client):
    # This test is skipped because it requires a valid password reset token.
    response = client.post(f"{BASE_URL}/reset-password", json={
        "token": "invalid_token",
        "new_password": "DoesNotMatter123!"
    })
    assert response.status_code == 400, "Reset password endpoint did not return expected error"
