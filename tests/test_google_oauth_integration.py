"""Integration tests for Google OAuth workflow."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import Response, AsyncClient
from starlette.status import (
    HTTP_200_OK, HTTP_401_UNAUTHORIZED, HTTP_400_BAD_REQUEST
)

from app.services.oauth_service import GoogleOAuthService
from app.models.user import User
from app.schemas.auth_schemas import GoogleAuthCallback


@pytest.fixture
def google_tokens():
    """Sample Google tokens response."""
    return {
        'access_token': 'ya29.test_access_token',
        'expires_in': 3599,
        'id_token': 'eyJhbGciOiJSUzI1NiIsImtpZCI6IjFiZDY4NWY1YThjOTk0ZGYxMjRmZjZiZWQwYTc1ZDBiMDVkOGUxOTEiLCJ0eXAiOiJKV1QifQ...',
        'refresh_token': '1//test_refresh_token',
        'scope': 'https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email openid',
        'token_type': 'Bearer'
    }


@pytest.fixture
def google_profile():
    """Sample Google profile data."""
    return {
        'sub': 'google123456789',
        'email': 'oauth_test@example.com',
        'email_verified': True,
        'name': 'OAuth Test',
        'picture': 'https://example.com/photo.jpg',
        'given_name': 'OAuth',
        'family_name': 'Test'
    }


@pytest.fixture
def mock_httpx_client():
    """Mock for httpx.AsyncClient."""
    with patch('httpx.AsyncClient') as mock_client:
        client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = client_instance
        yield client_instance


@pytest.mark.asyncio
class TestGoogleOAuthIntegration:
    """Integration tests for Google OAuth flow."""

    async def test_oauth_flow_new_user(
        self, 
        db_session, 
        async_client: AsyncClient, 
        mock_httpx_client, 
        google_tokens, 
        google_profile
    ):
        """Test complete OAuth flow for new user."""
        # 1. Mock token exchange response
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        mock_httpx_client.post.return_value = token_response
        
        # 2. Mock profile response
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        mock_httpx_client.get.return_value = profile_response
        
        # 3. Get authorization URL
        auth_url_response = await async_client.get("/auth/oauth/google/login")
        assert auth_url_response.status_code == HTTP_200_OK
        assert "auth_url" in auth_url_response.json()
        
        # 4. Simulate callback with code
        callback_response = await async_client.post(
            "/auth/oauth/google/callback",
            json={"code": "test_auth_code"}
        )
        assert callback_response.status_code == HTTP_200_OK
        assert "access_token" in callback_response.json()
        token = callback_response.json()["access_token"]
        
        # 5. Use token to access protected endpoint
        me_response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == HTTP_200_OK
        assert me_response.json()["email"] == google_profile["email"]
        assert me_response.json()["is_verified"] == True  # OAuth users are verified

    async def test_account_linking(
        self, 
        db_session, 
        test_user, 
        async_client: AsyncClient, 
        mock_httpx_client,
        google_tokens, 
        google_profile
    ):
        """Test linking an existing password account with Google."""
        # Setup mocks
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        
        # Configure mock to return different responses based on URL
        async def mock_request_handler(*args, **kwargs):
            if "token" in kwargs.get("url", ""):
                return token_response
            elif "userinfo" in kwargs.get("url", ""):
                return profile_response
            return MagicMock(spec=Response, status_code=404)
            
        mock_httpx_client.post.side_effect = mock_request_handler
        mock_httpx_client.get.side_effect = mock_request_handler
        
        # Link account
        link_response = await async_client.post(
            "/auth/link/google",
            json={
                "code": "test_auth_code",
                "password": test_user["password"]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        assert link_response.status_code == HTTP_200_OK
        
        # Verify user can now login with either method
        # 1. Original password still works
        password_login = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": test_user["password"]
            }
        )
        assert password_login.status_code == HTTP_200_OK
        
        # 2. OAuth login also works (simulate callback)
        callback_response = await async_client.post(
            "/auth/oauth/google/callback",
            json={"code": "test_auth_code"}
        )
        assert callback_response.status_code == HTTP_200_OK
        
        # Check that it's the same user account
        user_query = await db_session.execute(
            "SELECT * FROM users WHERE email = :email", 
            {"email": test_user["email"]}
        )
        users = user_query.fetchall()
        assert len(users) == 1  # Should only be one user with this email
        
    async def test_unlink_account(
        self, 
        db_session, 
        test_user,
        async_client: AsyncClient, 
        mock_httpx_client,
        google_tokens, 
        google_profile
    ):
        """Test unlinking a Google account."""
        # First link the account
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        
        # Configure mock to return different responses
        async def mock_request_handler(*args, **kwargs):
            if "token" in kwargs.get("url", ""):
                return token_response
            elif "userinfo" in kwargs.get("url", ""):
                return profile_response
            return MagicMock(spec=Response, status_code=404)
            
        mock_httpx_client.post.side_effect = mock_request_handler
        mock_httpx_client.get.side_effect = mock_request_handler
        
        # Link account
        await async_client.post(
            "/auth/link/google",
            json={
                "code": "test_auth_code",
                "password": test_user["password"]
            },
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        
        # Now unlink the account
        unlink_response = await async_client.post(
            "/auth/unlink/google",
            headers={"Authorization": f"Bearer {test_user['token']}"}
        )
        assert unlink_response.status_code == HTTP_200_OK
        assert unlink_response.json()["message"] == "Google account unlinked successfully"
        
        # Verify OAuth login no longer works
        callback_response = await async_client.post(
            "/auth/oauth/google/callback",
            json={"code": "test_auth_code"}
        )
        assert callback_response.status_code != HTTP_200_OK  # Should now fail or create new account
        
        # But password login still works
        password_login = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": test_user["password"]
            }
        )
        assert password_login.status_code == HTTP_200_OK

    async def test_oauth_only_user(
        self, 
        db_session, 
        async_client: AsyncClient, 
        mock_httpx_client, 
        google_tokens, 
        google_profile
    ):
        """Test user created via OAuth with no password."""
        # Configure mocks
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        
        async def mock_request_handler(*args, **kwargs):
            if "token" in kwargs.get("url", ""):
                return token_response
            elif "userinfo" in kwargs.get("url", ""):
                return profile_response
            return MagicMock(spec=Response, status_code=404)
            
        mock_httpx_client.post.side_effect = mock_request_handler
        mock_httpx_client.get.side_effect = mock_request_handler
        
        # Create user via OAuth
        callback_response = await async_client.post(
            "/auth/oauth/google/callback",
            json={"code": "test_auth_code"}
        )
        assert callback_response.status_code == HTTP_200_OK
        token = callback_response.json()["access_token"]
        
        # Check user profile
        me_response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == HTTP_200_OK
        
        # Verify password login doesn't work
        password_login = await async_client.post(
            "/auth/login",
            json={
                "email": google_profile["email"],
                "password": "any_password"  # Should be ignored
            }
        )
        assert password_login.status_code == HTTP_401_UNAUTHORIZED  # No password set
        
        # Check user in database
        user_query = await db_session.execute(
            "SELECT * FROM users WHERE email = :email", 
            {"email": google_profile["email"]}
        )
        user = user_query.fetchone()
        assert user is not None
        assert user.hashed_password is None  # OAuth-only user has no password
        assert user.auth_type == "google"