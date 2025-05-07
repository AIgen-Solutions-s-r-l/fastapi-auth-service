"""Tests for password management endpoints."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import status, BackgroundTasks
from jose import jwt
from sqlalchemy import select
from datetime import datetime, UTC, timedelta

from app.models.user import User, EmailVerificationToken, EmailChangeRequest, PasswordResetToken
from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
# Import the specific functions to be patched if needed, though patching by string path is usually preferred
# from app.routers.auth.password_management import verify_reset_token, reset_password
from app.services.email_service import EmailService

pytestmark = pytest.mark.asyncio

# Use the db fixture from conftest.py as db_session
@pytest.fixture
def db_session(db):
    return db


async def test_change_password_success(client, test_user_token):
    """Test successful password change."""
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": "newpassword123"
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["message"] == "Password updated successfully"


async def test_change_password_short_password(client, test_user_token):
    """Test password change with too short password."""
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": "short"  # Less than 8 characters
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    # The error message might be in different formats depending on the validation
    assert "New password must be at least 8 characters long" in str(data)


async def test_change_password_empty_password(client, test_user_token):
    """Test password change with empty password."""
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": ""  # Empty password
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    # The error message might be in different formats depending on the validation
    assert "New password must be at least 8 characters long" in str(data)


async def test_change_password_wrong_current_password(client, test_user_token, monkeypatch):
    """Test password change with wrong current password."""
    # Mock the update_user_password method to raise InvalidCredentialsError
    async def mock_update_password(*args, **kwargs):
        raise InvalidCredentialsError("Current password is incorrect")

    monkeypatch.setattr(
        "app.services.user_service.UserService.update_user_password",
        mock_update_password
    )
 
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "wrongpassword",
            "new_password": "newpassword123"
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert "InvalidCredentialsError" in str(data)


async def test_change_password_user_not_found(client, test_user_token, monkeypatch):
    """Test password change when user is not found."""
    # Mock the update_user_password method to raise UserNotFoundError
    async def mock_update_password(*args, **kwargs):
        raise UserNotFoundError("User not found")

    monkeypatch.setattr(
        "app.services.user_service.UserService.update_user_password",
        mock_update_password
    )
 
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": "newpassword123"
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert "User not found" in str(data)


async def test_change_password_update_failed(client, test_user_token, monkeypatch):
    """Test password change when update fails."""
    # Mock the update_user_password method to return False
    async def mock_update_password(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.services.user_service.UserService.update_user_password",
        mock_update_password
    )
 
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": "newpassword123"
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert "Failed to update password" in str(data)


async def test_change_password_unexpected_error(client, test_user_token, monkeypatch):
    """Test password change with unexpected error."""
    # Mock the update_user_password method to raise an unexpected error
    async def mock_update_password(*args, **kwargs):
        raise RuntimeError("Unexpected error")

    monkeypatch.setattr(
        "app.services.user_service.UserService.update_user_password",
        mock_update_password
    )
 
    response = await client.put( # Added await
        "/auth/users/password",
        json={
            "current_password": "password123",
            "new_password": "newpassword123"
        },
        headers={"Authorization": f"Bearer {test_user_token}"}
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert "Error changing password" in str(data)


async def test_password_reset_request_success(client, monkeypatch):
    """Test successful password reset request."""
    # Mock the create_password_reset_token function
    async def mock_create_token(*args, **kwargs):
        return "test_reset_token"

    # Mock the get_user_by_email method to return a user
    async def mock_get_user(*args, **kwargs):
        user = MagicMock()
        user.email = "test@example.com"
        return user

    # Mock the send_password_change_request method
    async def mock_send_email(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.services.user_service.create_password_reset_token",
        mock_create_token
    )
    monkeypatch.setattr(
        "app.services.user_service.UserService.get_user_by_email",
        mock_get_user
    )
    monkeypatch.setattr(
        "app.services.email_service.EmailService.send_password_change_request",
        mock_send_email
    )
 
    response = await client.post( # Added await
        "/auth/password-reset-request",
        json={"email": "test@example.com"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Password reset link sent to email if account exists" in data["message"]


async def test_password_reset_request_user_not_found(client, monkeypatch):
    """Test password reset request when user is not found."""
    # Mock the create_password_reset_token function to raise UserNotFoundError
    async def mock_create_token(*args, **kwargs):
        raise UserNotFoundError("User not found")

    monkeypatch.setattr(
        "app.services.user_service.create_password_reset_token",
        mock_create_token
    )
 
    response = await client.post( # Added await
        "/auth/password-reset-request",
        json={"email": "nonexistent@example.com"}
    )
 
    # Endpoint should return 200 OK even if user not found to avoid email enumeration
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Password reset link sent to email if account exists" in data["message"]


async def test_password_reset_request_jwt_error(client, monkeypatch):
    """Test password reset request with JWT error."""
    # Mock the create_password_reset_token function to raise JWTError
    async def mock_create_token(*args, **kwargs):
        raise jwt.JWTError("JWT error")

    monkeypatch.setattr(
        "app.services.user_service.create_password_reset_token",
        mock_create_token
    )
 
    response = await client.post( # Added await
        "/auth/password-reset-request",
        json={"email": "test@example.com"}
    )
 
    # Endpoint should return 200 OK even if internal error occurs to avoid email enumeration
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Password reset link sent to email if account exists" in data["message"]


async def test_password_reset_request_value_error(client, monkeypatch):
    """Test password reset request with value error."""
    # Mock the create_password_reset_token function to raise ValueError
    async def mock_create_token(*args, **kwargs):
        raise ValueError("Invalid value")

    monkeypatch.setattr(
        "app.services.user_service.create_password_reset_token",
        mock_create_token
    )
 
    response = await client.post( # Added await
        "/auth/password-reset-request",
        json={"email": "test@example.com"}
    )
 
    # Endpoint should return 200 OK even if internal error occurs to avoid email enumeration
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Password reset link sent to email if account exists" in data["message"]


async def test_reset_password_success(client, monkeypatch):
    """Test successful password reset."""
    # Mock verify_reset_token in the router's namespace
    async def mock_verify_token_router(db, token):
        return 1  # Return user_id 1
    monkeypatch.setattr("app.routers.auth.password_management.verify_reset_token", mock_verify_token_router)
    
    # Mock reset_password in the router's namespace
    async def mock_reset_password_router(*args, **kwargs):
        return True
    monkeypatch.setattr("app.routers.auth.password_management.reset_password", mock_reset_password_router)

    # Mock EmailService
    mock_email_service = MagicMock()
    mock_email_service_instance = MagicMock()
    mock_email_service_instance.send_password_reset_confirmation = AsyncMock(return_value=True)
    mock_email_service.return_value = mock_email_service_instance
    monkeypatch.setattr("app.routers.auth.password_management.EmailService", mock_email_service)

    # Mock the db.execute call ONLY for fetching the user (ID=1) for the confirmation email
    async def mock_execute_user_lookup_success(*args, **kwargs):
        # Assume this mock is ONLY called for the user lookup in this specific test
        mock_user_result = MagicMock()
        user_for_email = MagicMock(spec=User)
        user_for_email.id = 1
        user_for_email.email = "testconfirm@example.com"
        mock_user_result.scalar_one_or_none.return_value = user_for_email
        return mock_user_result
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute_user_lookup_success)
 
    response = await client.post(
        "/auth/password-reset",
        json={"token": "valid_token", "new_password": "newpassword123"}
    )
 
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "Password has been reset successfully" in data["message"]
 
    # Verify that the instance's send_password_reset_confirmation method was called
    assert mock_email_service_instance.send_password_reset_confirmation.call_count == 1


async def test_reset_password_invalid_token(client, monkeypatch):
    """Test password reset with invalid token."""
    # Mock verify_reset_token in the router's namespace to raise ValueError
    async def mock_verify_token_router_invalid(*args, **kwargs):
        raise ValueError("Invalid token")
    monkeypatch.setattr("app.routers.auth.password_management.verify_reset_token", mock_verify_token_router_invalid)
 
    response = await client.post(
        "/auth/password-reset",
        json={"token": "invalid_token", "new_password": "newpassword123"}
    )
 
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["detail"] == "Invalid user or invalid/expired token" # Corrected assertion detail


async def test_reset_password_update_failed(client, monkeypatch):
    """Test password reset when update fails."""
    # Mock verify_reset_token in the router's namespace to return 1
    async def mock_verify_token_router_ok(*args, **kwargs):
        return 1
    monkeypatch.setattr("app.routers.auth.password_management.verify_reset_token", mock_verify_token_router_ok)
    
    # Mock reset_password in the router's namespace to return False
    async def mock_reset_password_router_fails(*args, **kwargs):
        return False
    monkeypatch.setattr("app.routers.auth.password_management.reset_password", mock_reset_password_router_fails)
    # No db.execute mock needed here, router should raise 500 before email lookup

    response = await client.post(
        "/auth/password-reset",
        json={"token": "valid_token", "new_password": "newpassword123"}
    )
 
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert data["detail"] == "Failed to reset password"


async def test_reset_password_user_not_found(client, monkeypatch):
    """Test password reset when user is not found after token verification."""
    # Mock verify_reset_token in the router's namespace to return 999
    async def mock_verify_token_router_999(*args, **kwargs):
        return 999  # Non-existent user ID
    monkeypatch.setattr("app.routers.auth.password_management.verify_reset_token", mock_verify_token_router_999)

    # Mock reset_password in the router's namespace to return True
    async def mock_reset_password_router_ok(*args, **kwargs):
        return True
    monkeypatch.setattr("app.routers.auth.password_management.reset_password", mock_reset_password_router_ok)
    
    # Mock EmailService as it might be called if user is found (even if it's None later)
    mock_email_service = MagicMock()
    mock_email_service_instance = MagicMock()
    mock_email_service_instance.send_password_reset_confirmation = AsyncMock(return_value=True) # This won't be called if user is None
    mock_email_service.return_value = mock_email_service_instance
    monkeypatch.setattr("app.routers.auth.password_management.EmailService", mock_email_service)

    # Mock the db.execute call ONLY for fetching the user (ID=999) for the confirmation email
    async def mock_execute_user_lookup_notfound(*args, **kwargs): # Simplify signature
        # Assume this mock is ONLY called for the user lookup (ID 999) in this specific test
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = None # User not found
        return mock_user_result
    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute_user_lookup_notfound)
 
    response = await client.post( # Added await
        "/auth/password-reset",
        json={"token": "valid_token", "new_password": "newpassword123"}
    )
 
    # Should return 200 even if user not found for confirmation email
    assert response.status_code == status.HTTP_200_OK


async def test_reset_password_unexpected_error(client, monkeypatch):
    """Test password reset with unexpected error."""
    # Mock verify_reset_token in the router's namespace to raise RuntimeError
    async def mock_verify_token_router_runtime_error(*args, **kwargs):
        raise RuntimeError("Unexpected error")
    monkeypatch.setattr("app.routers.auth.password_management.verify_reset_token", mock_verify_token_router_runtime_error)
    # No db.execute mock needed here, exception should be caught by generic handler
 
    response = await client.post(
        "/auth/password-reset",
        json={"token": "valid_token", "new_password": "newpassword123"}
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert data["detail"] == "Error processing password reset"
