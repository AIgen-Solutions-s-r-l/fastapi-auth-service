"""Tests for Google OAuth API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import FastAPI
from httpx import AsyncClient
from starlette.status import (
    HTTP_200_OK, HTTP_201_CREATED, HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN, HTTP_500_INTERNAL_SERVER_ERROR
)
from jose import jwt

from app.main import app
from app.core.config import settings
from app.models.user import User
from app.core.security import create_access_token


@pytest.fixture
def google_auth_url():
    """Sample Google authorization URL."""
    return "https://accounts.google.com/o/oauth2/auth?response_type=code&client_id=test_client_id&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fgoogle%2Fcallback&scope=openid+email+profile&state=test_state"


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
        'email': 'test@example.com',
        'email_verified': True,
        'name': 'Test User',
        'picture': 'https://example.com/photo.jpg',
        'given_name': 'Test',
        'family_name': 'User'
    }


@pytest.fixture
def mock_google_oauth_service():
    """Mock GoogleOAuthService for testing."""
    with patch('app.routers.auth_router.GoogleOAuthService') as mock_service:
        service_instance = AsyncMock()
        mock_service.return_value = service_instance
        yield service_instance


class TestGoogleOAuthEndpoints:
    """Tests for Google OAuth API endpoints."""

    @pytest.mark.asyncio
    async def test_google_login(self, test_app_client, mock_google_oauth_service, google_auth_url):
        """Test the Google login endpoint."""
        # Setup mock
        mock_google_oauth_service.get_authorization_url.return_value = google_auth_url

        # Make request
        response = await test_app_client.get("/auth/oauth/google/login")
        
        # Check response
        assert response.status_code == HTTP_200_OK
        assert "auth_url" in response.json()
        
        # Verify mock was called correctly
        mock_google_oauth_service.get_authorization_url.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_google_login_with_custom_redirect(
        self, test_app_client, mock_google_oauth_service, google_auth_url
    ):
        """Test the Google login endpoint with custom redirect URI."""
        # Setup mock
        custom_redirect = "https://custom.example.com/callback"
        mock_google_oauth_service.get_authorization_url.return_value = google_auth_url

        # Make request
        response = await test_app_client.get(
            "/auth/oauth/google/login", params={"redirect_uri": custom_redirect}
        )
        
        # Check response
        assert response.status_code == HTTP_200_OK
        assert "auth_url" in response.json()
        
        # Verify mock was called with custom redirect
        mock_google_oauth_service.get_authorization_url.assert_called_once_with(custom_redirect)

    @pytest.mark.asyncio
    async def test_google_login_error(self, test_app_client, mock_google_oauth_service):
        """Test the Google login endpoint error handling."""
        # Setup mock to raise exception
        mock_google_oauth_service.get_authorization_url.side_effect = Exception("OAuth error")

        # Make request
        response = await test_app_client.get("/auth/oauth/google/login")
        
        # Check error response
        assert response.status_code == HTTP_500_INTERNAL_SERVER_ERROR
        assert "Error generating Google login URL" in response.json().get("message", "")

    @pytest.mark.asyncio
    async def test_google_callback(
        self, test_app_client, mock_google_oauth_service, test_user
    ):
        """Test successful Google OAuth callback."""
        # Setup mock
        jwt_token = "test.jwt.token"
        # Create a User object from the test_user dictionary
        user_obj = type('User', (), {
            'id': 1,
            'username': test_user['username'],
            'email': test_user['email'],
            'is_verified': True,
            'is_admin': False
        })
        mock_google_oauth_service.login_with_google.return_value = (user_obj, jwt_token)
        
        # Make request
        response = await test_app_client.post(
            "/auth/oauth/google/callback",
            json={"code": "test_auth_code"}
        )
        
        # Check response
        assert response.status_code == HTTP_200_OK
        assert response.json()["access_token"] == jwt_token
        assert response.json()["token_type"] == "bearer"
        
        # Verify mock was called correctly
        mock_google_oauth_service.login_with_google.assert_called_once_with("test_auth_code")

    @pytest.mark.asyncio
    async def test_google_callback_error(self, test_app_client, mock_google_oauth_service):
        """Test Google OAuth callback error handling."""
        # Setup mock to raise exception
        mock_google_oauth_service.login_with_google.side_effect = Exception("Invalid code")
        
        # Make request
        response = await test_app_client.post(
            "/auth/oauth/google/callback",
            json={"code": "invalid_code"}
        )
        
        # Check error response
        assert response.status_code == HTTP_400_BAD_REQUEST
        assert "Error processing Google callback" in response.json().get("message", "")

    @pytest.mark.asyncio
    async def test_link_google_account(
        self, test_app_client, mock_google_oauth_service, test_user, google_profile, google_tokens
    ):
        """Test linking a Google account to an existing user."""
        # Create access token for test user
        token = create_access_token(
            data={"sub": test_user['email'], "id": 1}  # Use dictionary access and assume id=1
        )
        
        # Setup mocks
        mock_google_oauth_service.exchange_code_for_tokens.return_value = google_tokens
        mock_google_oauth_service.get_user_profile.return_value = google_profile
        
        # Patch verify_password to return True
        with patch('app.routers.auth_router.verify_password', return_value=True):
            # Make request
            response = await test_app_client.post(
                "/auth/link/google",
                json={"provider": "google", "code": "test_auth_code", "password": "testpassword"},
                headers={"Authorization": f"Bearer {token}"}
            )
        
        # Check response
        assert response.status_code == HTTP_200_OK
        assert response.json()["message"] == "Google account linked successfully"
        
        # Verify mocks were called correctly
        mock_google_oauth_service.exchange_code_for_tokens.assert_called_once_with("test_auth_code")
        mock_google_oauth_service.get_user_profile.assert_called_once_with(google_tokens["access_token"])
        mock_google_oauth_service.link_google_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_link_google_account_wrong_password(
        self, test_app_client, mock_google_oauth_service, test_user
    ):
        """Test linking with wrong password."""
        # Create access token for test user
        token = create_access_token(
            data={"sub": test_user['email'], "id": 1}  # Use dictionary access and assume id=1
        )
        
        # Patch verify_password to return False
        with patch('app.routers.auth_router.verify_password', return_value=False):
            # Make request
            response = await test_app_client.post(
                "/auth/link/google",
                json={"provider": "google", "code": "test_auth_code", "password": "wrong_password"},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Check response
            assert response.status_code == HTTP_401_UNAUTHORIZED
            assert "Invalid password" in response.json().get("message", "")

    @pytest.mark.asyncio
    async def test_unlink_google_account(
        self, test_app_client, mock_google_oauth_service, test_user
    ):
        """Test unlinking a Google account."""
        # Create access token for test user
        token = create_access_token(
            data={"sub": test_user['email'], "id": 1}  # Use dictionary access and assume id=1
        )
        
        # Make request
        response = await test_app_client.post(
            "/auth/unlink/google",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Check response
        assert response.status_code == HTTP_200_OK
        assert response.json()["message"] == "Google account unlinked successfully"
        
        # Verify mock was called correctly
        mock_google_oauth_service.unlink_google_account.assert_called_once()

    @pytest.mark.asyncio
    async def test_unlink_google_account_error(
        self, test_app_client, mock_google_oauth_service, test_user
    ):
        """Test error handling for unlinking a Google account."""
        # Create access token for test user
        token = create_access_token(
            data={"sub": test_user['email'], "id": 1}  # Use dictionary access and assume id=1
        )
        
        # Setup mock to raise exception
        mock_google_oauth_service.unlink_google_account.side_effect = Exception("Cannot unlink")
        
        # Make request
        response = await test_app_client.post(
            "/auth/unlink/google",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Check error response
        assert response.status_code == HTTP_400_BAD_REQUEST
        assert "Error unlinking Google account" in response.json().get("message", "")