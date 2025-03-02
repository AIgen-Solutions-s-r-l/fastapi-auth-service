import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from jose import jwt
from datetime import datetime, timedelta, timezone

# Directly patch specific functions rather than relying on API calls
pytestmark = pytest.mark.asyncio

# Target lines 47-65: Login function failure paths
@patch("app.routers.auth_router.authenticate_user_by_username_or_email")
@patch("app.routers.auth_router.logger")
async def test_login_with_none_user(mock_logger, mock_auth):
    from app.routers.auth_router import login
    from app.schemas.auth_schemas import LoginRequest
    
    # Set up to return None
    mock_auth.return_value = None
    
    # Call the function directly
    credentials = LoginRequest(email="test@example.com", password="password")
    
    # Create mock DB session
    db = MagicMock()
    
    # This should reach the handler for user not found
    with pytest.raises(Exception):
        await login(credentials, db)
    
    # Verify logger was called for failed login
    mock_logger.warning.assert_called_once()

# Target lines 152-153: Get user details with None user
@patch("app.routers.auth_router.get_user_by_username")
@patch("app.routers.auth_router.logger")
async def test_get_user_details_none_user(mock_logger, mock_get_user):
    from app.routers.auth_router import get_user_details
    from app.core.exceptions import UserNotFoundError
    
    # Setup to return None user
    mock_get_user.return_value = None
    
    # Create mock DB session
    db = MagicMock()
    
    # This should raise exception for null user
    with pytest.raises(Exception):
        await get_user_details("nonexistent_user", db)
    
    # Verify logger was called for error
    mock_logger.error.assert_called_once()

# Target lines 232-239: Email change function error handling
@patch("app.routers.auth_router.verify_jwt_token") 
@patch("app.routers.auth_router.UserService")
@patch("app.routers.auth_router.logger")
async def test_change_email_unauthorized(mock_logger, mock_service, mock_verify):
    from app.routers.auth_router import change_email
    from app.schemas.auth_schemas import EmailChange
    
    # Mock JWT verification to return non-admin payload for a different user
    mock_verify.return_value = {
        "sub": "different_user",
        "id": 123,
        "is_admin": False
    }
    
    # Create mock DB and token
    db = MagicMock()
    token = "valid.token.here"
    
    # Create test data
    email_change = EmailChange(current_password="password", new_email="new@example.com")
    
    # Call function with a username that doesn't match the token
    with pytest.raises(Exception):
        await change_email("testuser", email_change, db, token)
    
    # Verify logger was called
    mock_logger.error.assert_called_once()

# Target lines 287-291, 318-322: Password change and User deletion error handling
@patch("app.routers.auth_router.update_user_password")
@patch("app.routers.auth_router.logger")
async def test_change_password_errors(mock_logger, mock_update):
    from app.routers.auth_router import change_password
    from app.schemas.auth_schemas import PasswordChange
    from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
    
    # Setup to raise error
    mock_update.side_effect = UserNotFoundError("Test user")
    
    # Create mock DB and token
    db = MagicMock()
    token = "valid.token.here"
    
    # Create test data
    passwords = PasswordChange(current_password="current", new_password="new")
    
    # Call function with error
    with pytest.raises(Exception):
        await change_password("testuser", passwords, db, token)
    
    # Reset mock for next test
    mock_update.side_effect = InvalidCredentialsError()
    with pytest.raises(Exception):
        await change_password("testuser", passwords, db, token)
    
    # Verify logger was called
    assert mock_logger.error.call_count >= 1

@patch("app.routers.auth_router.delete_user")
@patch("app.routers.auth_router.logger")
async def test_delete_user_errors(mock_logger, mock_delete):
    from app.routers.auth_router import remove_user
    from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
    
    # Setup to raise error
    mock_delete.side_effect = UserNotFoundError("Test user")
    
    # Create mock DB and token
    db = MagicMock()
    token = "valid.token.here"
    
    # Call function with error
    with pytest.raises(Exception):
        await remove_user("testuser", "password", db, token)
    
    # Reset mock for next test
    mock_delete.side_effect = InvalidCredentialsError()
    with pytest.raises(Exception):
        await remove_user("testuser", "password", db, token)
    
    # Verify logger was called
    assert mock_logger.error.call_count >= 1

# Target line 490: Get current user profile - admin user requesting another user not found
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
@patch("app.routers.auth_router.get_user_by_email")
@patch("app.routers.auth_router.logger")
async def test_get_current_user_profile_admin_user_not_found(mock_logger, mock_get_by_email, mock_get_by_username, mock_verify):
    from app.routers.auth_router import get_current_user_profile
    from app.core.exceptions import UserNotFoundError
    
    # Setup admin user with email
    admin_email = "admin@example.com"
    mock_verify.return_value = {
        "sub": admin_email,
        "id": 999,
        "is_admin": True
    }
    
    # Setup admin user object
    admin_user = MagicMock()
    admin_user.id = 999
    admin_user.username = "admin_user"
    admin_user.email = admin_email
    
    # Mock get_user_by_email to return admin user when admin email is passed
    mock_get_by_email.side_effect = lambda db, email: admin_user if email == admin_email else None
    
    # Mock get_user_by_username to always return None for this test
    mock_get_by_username.return_value = None
    
    # Create mock DB and token
    db = MagicMock()
    token = "valid.token.here"
    
    # Call function with non-existent user ID
    with pytest.raises(Exception):
        await get_current_user_profile(456, token, db)
    
    # Verify logger was called
    mock_logger.error.assert_called_once()

# Target lines 811-858: Get user email by ID
@patch("app.log.logging.logger")  # Patch the directly imported module
async def test_get_email_by_id_not_found(mock_logger):
    from app.routers.auth_router import get_email_by_user_id
    from fastapi import HTTPException
    
    # Create a mock DB session with execute method using AsyncMock
    db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    
    # Use AsyncMock for the execute method
    db.execute = AsyncMock(return_value=mock_result)
    
    # Call function with ID of a user that doesn't exist
    with pytest.raises(HTTPException) as exc_info:
        await get_email_by_user_id(999, db)
    
    # Verify exception is 404 Not Found
    assert exc_info.value.status_code == 404

@patch("app.routers.auth_router.logger")
async def test_get_email_by_id_exception(mock_logger):
    from app.routers.auth_router import get_email_by_user_id
    
    # Create a mock DB session that raises exception
    db = MagicMock()
    db.execute.side_effect = Exception("Database error")
    
    # Call function that will trigger the exception
    with pytest.raises(Exception):
        await get_email_by_user_id(123, db)
    
    # Verify logger was called
    mock_logger.error.assert_called_once()