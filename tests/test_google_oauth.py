"""Tests for Google OAuth integration."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import Response
from fastapi import HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_400_BAD_REQUEST

from app.services.oauth_service import GoogleOAuthService
from app.models.user import User


@pytest.fixture
def mock_httpx_client():
    """Mock for httpx.AsyncClient."""
    with patch('httpx.AsyncClient') as mock_client:
        client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = client_instance
        yield client_instance


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


class TestGoogleOAuthService:
    """Tests for GoogleOAuthService."""

    async def test_get_authorization_url(self, db_session):
        """Test getting Google authorization URL."""
        service = GoogleOAuthService(db_session)
        
        # Test with default redirect URI
        url = await service.get_authorization_url()
        assert "accounts.google.com/o/oauth2/auth" in url
        assert "response_type=code" in url
        
        # Test with custom redirect URI
        custom_url = await service.get_authorization_url("https://custom.example.com/callback")
        assert "redirect_uri=https://custom.example.com/callback" in custom_url

    async def test_exchange_code_for_tokens(self, db_session, mock_httpx_client, google_tokens):
        """Test exchanging authorization code for tokens."""
        # Setup mock response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = google_tokens
        mock_httpx_client.post.return_value = mock_response
        
        service = GoogleOAuthService(db_session)
        tokens = await service.exchange_code_for_tokens("test_auth_code")
        
        assert tokens == google_tokens
        mock_httpx_client.post.assert_called_once()
        
        # Test error response
        mock_response.status_code = 400
        mock_response.text = "Invalid code"
        
        with pytest.raises(HTTPException) as excinfo:
            await service.exchange_code_for_tokens("invalid_code")
        
        assert excinfo.value.status_code == HTTP_400_BAD_REQUEST

    async def test_get_user_profile(self, db_session, mock_httpx_client, google_profile):
        """Test getting user profile from Google."""
        # Setup mock response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = google_profile
        mock_httpx_client.get.return_value = mock_response
        
        service = GoogleOAuthService(db_session)
        profile = await service.get_user_profile("test_access_token")
        
        assert profile == google_profile
        mock_httpx_client.get.assert_called_once()
        
        # Test error response
        mock_response.status_code = 401
        mock_response.text = "Invalid token"
        
        with pytest.raises(HTTPException) as excinfo:
            await service.get_user_profile("invalid_token")
        
        assert excinfo.value.status_code == HTTP_400_BAD_REQUEST

    async def test_find_or_create_user_new(self, db_session, google_profile):
        """Test finding or creating a new user from Google profile."""
        service = GoogleOAuthService(db_session)
        
        # Ensure user doesn't exist yet
        user = await service.find_or_create_user(google_profile)
        
        assert user is not None
        assert user.google_id == google_profile['sub']
        assert user.email == google_profile['email']
        assert user.auth_type == 'google'
        assert user.hashed_password is None
        assert user.is_verified is True

    async def test_find_or_create_user_existing_by_google_id(self, db_session, google_profile, test_user):
        """Test finding existing user by Google ID."""
        # Get user from database using SQLAlchemy ORM
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_user['email'])
        result = await db_session.execute(stmt)
        user_obj = result.scalars().first()
        
        # Update user with Google ID
        user_obj.google_id = google_profile['sub']
        user_obj.auth_type = 'both'
        await db_session.commit()
        
        service = GoogleOAuthService(db_session)
        user = await service.find_or_create_user(google_profile)
        
        assert user is not None
        assert user.google_id == google_profile['sub']

    async def test_find_or_create_user_existing_by_email(self, db_session, google_profile, test_user):
        """Test finding existing user by email and updating with Google ID."""
        # Get user from database using SQLAlchemy ORM
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_user['email'])
        result = await db_session.execute(stmt)
        user_obj = result.scalars().first()
        
        # Update user with Google profile email
        user_obj.email = google_profile['email']
        user_obj.is_verified = False  # To test it gets updated
        await db_session.commit()
        
        service = GoogleOAuthService(db_session)
        user = await service.find_or_create_user(google_profile)
        
        assert user is not None
        assert user.google_id == google_profile['sub']
        assert user.auth_type == 'both'  # Because test_user has a password
        assert user.is_verified is True  # Should be updated
        
    async def test_link_google_account(self, db_session, google_profile, test_user):
        """Test linking a Google account to an existing user."""
        # Get user from database using SQLAlchemy ORM
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_user['email'])
        result = await db_session.execute(stmt)
        user_obj = result.scalars().first()
        
        # Ensure no Google ID initially
        user_obj.google_id = None
        user_obj.auth_type = 'password'
        await db_session.commit()
        
        service = GoogleOAuthService(db_session)
        updated_user = await service.link_google_account(user_obj, google_profile)
        
        # Refresh the user from the database
        await db_session.refresh(user_obj)
        
        # Verify user has been updated with Google info
        assert updated_user.google_id == google_profile['sub']
        assert updated_user.auth_type == 'both'
        assert updated_user.is_verified is True
        
    async def test_unlink_google_account(self, db_session, google_profile, test_user):
        """Test unlinking a Google account from an existing user."""
        # Get user from database using SQLAlchemy ORM
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_user['email'])
        result = await db_session.execute(stmt)
        user_obj = result.scalars().first()
        
        # Set Google ID
        user_obj.google_id = google_profile['sub']
        user_obj.auth_type = 'both'
        await db_session.commit()
        
        # Refresh the user object
        await db_session.refresh(user_obj)
        
        service = GoogleOAuthService(db_session)
        updated_user = await service.unlink_google_account(user_obj)
        
        # Refresh the user from the database
        await db_session.refresh(user_obj)
        
        # Verify user has had Google info removed
        assert updated_user.google_id is None
        assert updated_user.auth_type == 'password'
        
    async def test_login_with_google_new_user(self, db_session,
                                             mock_httpx_client, google_tokens, google_profile):
        """Test logging in with Google as a new user."""
        # Mock token exchange response
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        mock_httpx_client.post.return_value = token_response
        
        # Mock profile response
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        mock_httpx_client.get.return_value = profile_response
        
        service = GoogleOAuthService(db_session)
        user, token = await service.login_with_google("test_auth_code")
        
        # Verify a new user was created with Google profile data
        assert user is not None
        assert user.email == google_profile['email']
        assert user.google_id == google_profile['sub']
        assert user.auth_type == 'google'
        assert token is not None  # Just check token is returned, not its exact value
        
    async def test_login_with_google_existing_user(self, db_session,
                                                 mock_httpx_client, google_tokens,
                                                 google_profile, test_user):
        """Test logging in with Google as an existing user."""
        # Get user from database using SQLAlchemy ORM
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_user['email'])
        result = await db_session.execute(stmt)
        user_obj = result.scalars().first()
        
        # Set Google ID for existing user
        user_obj.google_id = google_profile['sub']
        user_obj.auth_type = 'both'
        await db_session.commit()
        
        # Mock token exchange response
        token_response = MagicMock(spec=Response)
        token_response.status_code = 200
        token_response.json.return_value = google_tokens
        mock_httpx_client.post.return_value = token_response
        
        # Mock profile response
        profile_response = MagicMock(spec=Response)
        profile_response.status_code = 200
        profile_response.json.return_value = google_profile
        mock_httpx_client.get.return_value = profile_response
        
        service = GoogleOAuthService(db_session)
        user, token = await service.login_with_google("test_auth_code")
        
        # Verify existing user was found
        assert user is not None
        assert user.email == test_user['email']  # User email remains unchanged because we find by Google ID
        assert user.google_id == google_profile['sub']  # Google ID should match
        assert token is not None