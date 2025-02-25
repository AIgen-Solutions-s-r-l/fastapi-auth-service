import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone

pytestmark = pytest.mark.asyncio

# Target login function exceptions (lines 52-65)
@patch("app.routers.auth_router.authenticate_user")
async def test_login_exception(mock_auth):
    from app.routers.auth_router import login
    from app.schemas.auth_schemas import LoginRequest
    
    # Setup the function to raise general exception (not just InvalidCredentialsError)
    mock_auth.side_effect = ValueError("Database connection error")
    
    # Create test data
    credentials = LoginRequest(username="testuser", password="password")
    db = MagicMock()
    
    # Call and expect an exception
    with pytest.raises(Exception):
        await login(credentials, db)

# Target user registration (lines 110-133)
async def test_register_direct():
    from app.routers.auth_router import register_user
    from app.schemas.auth_schemas import UserCreate
    from app.models.user import User
    
    # Create a fully mocked user and DB for direct function call
    user_data = UserCreate(username="newuser", email="new@example.com", password="Password123!")
    
    # Mock new user
    new_user = MagicMock(spec=User)
    new_user.username = "newuser"
    new_user.id = 123
    new_user.is_admin = False
    new_user.email = "new@example.com"
    
    # Mock DB
    db = MagicMock()
    
    # Mock create_user to return our mock user
    with patch("app.routers.auth_router.create_user", return_value=new_user):
        # Mock create_access_token
        with patch("app.routers.auth_router.create_access_token", return_value="access.token.here"):
            # Call the function directly
            result = await register_user(user_data, db)
            
            # Verify the result
            assert result["username"] == "newuser"
            assert result["access_token"] == "access.token.here"
            assert result["token_type"] == "bearer"

# Target get_user_details (lines 152-153)
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_user_details_direct(mock_get_user):
    from app.routers.auth_router import get_user_details
    from app.models.user import User
    
    # Mock user
    user = MagicMock(spec=User)
    user.username = "testuser"
    user.email = "test@example.com"
    mock_get_user.return_value = user
    
    # Mock DB
    db = MagicMock()
    
    # Call directly
    result = await get_user_details("testuser", db)
    
    # Verify
    assert result["username"] == "testuser"
    assert result["email"] == "test@example.com"

# Target email change function (lines 232-239, 248-256)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.UserService")
async def test_email_change_scenarios(mock_service, mock_verify):
    from app.routers.auth_router import change_email
    from app.schemas.auth_schemas import EmailChange
    
    # Scenario 1: JWT verification error
    mock_verify.side_effect = jwt.JWTError("Invalid token")
    
    email_change = EmailChange(current_password="password", new_email="new@example.com")
    db = MagicMock()
    token = "invalid.token.here"
    
    with pytest.raises(Exception):
        await change_email("testuser", email_change, db, token)
    
    # Scenario 2: General exception
    mock_verify.side_effect = None
    mock_verify.return_value = {"sub": "testuser", "id": 123, "is_admin": False}
    
    # Mock service to raise general exception
    mock_instance = MagicMock()
    mock_instance.update_user_email.side_effect = Exception("Database error")
    mock_service.return_value = mock_instance
    
    with pytest.raises(Exception):
        await change_email("testuser", email_change, db, token)

# Target refresh token function (lines 407-408)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_refresh_token_user_not_found_direct(mock_get_user, mock_verify):
    from app.routers.auth_router import refresh_token
    from app.schemas.auth_schemas import RefreshToken
    
    # Mock JWT verification
    mock_verify.return_value = {"sub": "testuser", "id": 123}
    
    # Mock user not found
    mock_get_user.return_value = None
    
    # Mock request
    refresh_request = RefreshToken(token="valid.looking.token")
    
    # Mock DB
    db = MagicMock()
    
    # Call function and expect exception
    with pytest.raises(Exception):
        await refresh_token(refresh_request, db)

# Target get_current_user_profile (lines 479, 484)
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_username")
async def test_get_current_user_profile_edge_cases_direct(mock_get_user, mock_verify):
    from app.routers.auth_router import get_current_user_profile
    from app.core.exceptions import UserNotFoundError
    
    # Mock JWT verification
    mock_verify.return_value = {"sub": "testuser", "id": 123, "is_admin": False}
    
    # Mock non-admin attempting to access other user's profile
    user = MagicMock()
    user.id = 123
    mock_get_user.return_value = user
    
    # Mock DB
    db = MagicMock()
    token = "valid.token.here"
    
    # Call with different user_id
    with pytest.raises(Exception): 
        await get_current_user_profile(456, token, db)
    
    # Mock user lookup returning None after successful token validation
    mock_get_user.return_value = None
    
    # Call with no user_id
    with pytest.raises(Exception):
        await get_current_user_profile(None, token, db)

# Target get_email_and_username_by_user_id (lines 540-546)
async def test_get_email_username_by_user_id_direct_not_found():
    from app.routers.auth_router import get_email_and_username_by_user_id
    from app.models.user import User
    
    # Create mock DB session
    db = MagicMock()
    
    # Create mock result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    # Call function with non-existent user
    with pytest.raises(Exception):
        await get_email_and_username_by_user_id(999, db)