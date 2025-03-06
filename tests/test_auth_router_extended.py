import uuid
import pytest
import sqlalchemy
from contextlib import asynccontextmanager
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from httpx import AsyncClient
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy.sql import select

from app.core.exceptions import UserNotFoundError, InvalidCredentialsError
from app.core.security import create_access_token
from app.models.user import User
from app.core.database import get_db
from app.main import app

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def client(async_client: AsyncClient):
    return async_client

# No need to redefine test_user - it's imported from conftest.py

# Test login failures
async def test_login_invalid_credentials(client: AsyncClient, test_user):
    # Test login with incorrect password
    response = await client.post("/auth/login", json={
        "email": test_user["email"],
        "password": "WrongPassword123!"
    })
    assert response.status_code == 401, "Expected 401 Unauthorized"
    
    # Test login with non-existent email
    response = await client.post("/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "TestPassword123!"
    })
    assert response.status_code == 401, "Expected 401 Unauthorized"

# Test user retrieval for non-existent user
# Patch the get_user_by_email function to raise UserNotFoundError for non-existent users
@patch("app.routers.auth_router.get_user_by_email")
async def test_get_nonexistent_user(mock_get_user, client: AsyncClient, test_user):
    # Make the get_user_by_email function raise UserNotFoundError
    mock_get_user.side_effect = UserNotFoundError("User not found")
    
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.get("/auth/users/by-email/nonexistent@example.com", headers=headers)
    assert response.status_code == 404, "Expected 404 Not Found"

# Test failed password change
async def test_change_password_wrong_current(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.put(
        "/auth/users/change-password",
        json={"current_password": "WrongPassword123!", "new_password": "NewPassword456!"},
        headers=headers
    )
    assert response.status_code == 401, "Expected 401 Unauthorized for wrong current password"

# Test user deletion with wrong password
async def test_delete_user_wrong_password(client: AsyncClient, test_user):
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await client.delete(
        "/auth/users/delete-account",
        params={"password": "WrongPassword123!"},
        headers=headers
    )
    assert response.status_code == 401, "Expected 401 Unauthorized for wrong password"

# Test logout with invalid token
async def test_logout_invalid_token(client: AsyncClient):
    # Create an expired token
    expired_token = create_access_token(
        data={"sub": "test@example.com", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        expires_delta=timedelta(minutes=-60)  # Negative delta for expired token
    )
    
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await client.post("/auth/logout", headers=headers)
    assert response.status_code == 401, "Expected 401 Unauthorized for expired token"

# Test refresh token functionality
async def test_refresh_token_functionality(client: AsyncClient, test_user):
    # Test with valid token
    response = await client.post("/auth/refresh", json={"token": test_user["token"]})
    assert response.status_code == 200, "Token refresh should succeed with valid token"
    data = response.json()
    assert "access_token" in data, "Response should contain a new access token"
    
    # Test with invalid token
    response = await client.post("/auth/refresh", json={"token": "invalid.token.format"})
    assert response.status_code == 401, "Expected 401 Unauthorized for invalid token"

# Test current user profile with invalid token
async def test_get_current_user_profile_invalid_token(client: AsyncClient):
    headers = {"Authorization": "Bearer invalid.token.format"}
    response = await client.get("/auth/me", headers=headers)
    assert response.status_code == 401, "Expected 401 Unauthorized for invalid token"

# Test get current user profile with admin user checking another user
@patch("app.routers.auth_router.verify_jwt_token")
@patch("app.routers.auth_router.get_user_by_email")
@patch("app.routers.auth_router.get_db")
async def test_get_current_user_profile_admin_access(
    mock_get_db, mock_get_user, mock_verify_token, client: AsyncClient, test_user
):
    # Create admin token
    admin_token = create_access_token(
        data={
            "sub": "admin@example.com",
            "id": 999,
            "is_admin": True,
            "exp": datetime.now(timezone.utc).timestamp() + 3600
        }
    )
    
    # Mock JWT verification to return admin payload
    mock_verify_token.return_value = {
        "sub": "admin@example.com",
        "id": 999,
        "is_admin": True
    }
    
    # Create actual User model instances instead of mocks
    from app.models.user import User
    
    admin_user = User(
        id=999,
        email="admin@example.com",
        is_admin=True,
        is_verified=True,
        hashed_password="dummy_hash"
    )

    target_user = User(
        id=123,
        email="target@example.com",
        is_admin=False,
        is_verified=True,
        hashed_password="dummy_hash"
    )
    
    # Setup mock database session
    mock_db_session = AsyncMock()
    
    # Create simple result objects that directly return the user instances
    class MockResult:
        def __init__(self, user):
            self.user = user
            
        async def scalar_one_or_none(self):
            return self.user
            
        def scalars(self):
            return self
            
    admin_result = MockResult(admin_user)
    target_result = MockResult(target_user)

    # Set up mock_get_user to return proper users
    async def get_user_side_effect(db_session, email):
        if email == "admin@example.com":
            return admin_user
        elif email == "target@example.com":
            return target_user
        return None
    
    mock_get_user.side_effect = get_user_side_effect
    
    # Setup the database session with async context manager
    async def mock_execute(query, **kwargs):
        # Create a simple result class that returns the actual user
        class Result:
            def __init__(self, user):
                self._user = user

            def scalar_one_or_none(self):
                return self._user

            def scalars(self):
                return self

            def all(self):
                return [self._user]

        # Get SQL and parameters for debugging
        sql = str(query)
        params = kwargs.get('parameters', {})
        print(f"\nDEBUG SQL: {sql}")
        print(f"DEBUG params: {params}")

        # Extract bind parameters from the query
        if hasattr(query, 'compile'):
            compiled = query.compile()
            bind_params = compiled.params
            print(f"DEBUG bind params: {bind_params}")

            # Handle user lookup by ID
            if 'users.id' in sql and 'id_1' in bind_params:
                user_id = bind_params['id_1']
                print(f"DEBUG: Looking up user by ID: {user_id}")
                if user_id == target_user.id:
                    print("DEBUG: Returning target user")
                    return Result(target_user)
                elif user_id == admin_user.id:
                    print("DEBUG: Returning admin user")
                    return Result(admin_user)

            # Handle user lookup by email
            if 'users.email' in sql and 'email_1' in bind_params:
                email = bind_params['email_1']
                print(f"DEBUG: Looking up user by email: {email}")
                if email == admin_user.email:
                    print("DEBUG: Returning admin user")
                    return Result(admin_user)
                elif email == target_user.email:
                    print("DEBUG: Returning target user")
                    return Result(target_user)

        print("DEBUG: No match found, returning empty result")
        return Result(None)

    # Attach the execute mock to the session
    mock_db_session.execute = AsyncMock(side_effect=mock_execute)
    
    # Create an async context manager for the database session
    @asynccontextmanager
    async def mock_db_context():
        try:
            print("\nDEBUG: Entering mock DB context")
            yield mock_db_session
        finally:
            print("DEBUG: Exiting mock DB context")
    
    # Override the database dependency at the app level
    async def override_get_db():
        print("\nDEBUG: get_db dependency called")
        async with mock_db_context() as session:
            print("DEBUG: yielding database session")
            yield session

    # Store original dependency and override
    original_get_db = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db

    try:
        # Make the request as admin viewing another user's profile
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await client.get("/auth/me?user_id=123", headers=headers)

        # Verify expected behavior
        assert response.status_code == 200, "Admin should be able to view other profiles"
        data = response.json()
        assert data["email"] == "target@example.com", "Should return the target user's email"

    finally:
        # Restore original dependency
        if original_get_db is not None:
            app.dependency_overrides[get_db] = original_get_db
        else:
            del app.dependency_overrides[get_db]
    data = response.json()
    assert data["email"] == "target@example.com", "Should return the target user's email"

# Test get email by user ID
async def test_get_email_by_user_id(client: AsyncClient, test_user):
    # Use an invalid user ID directly
    nonexistent_id = 999999  # Assuming this user ID doesn't exist
    response = await client.get(f"/auth/users/{nonexistent_id}/email")
    assert response.status_code == 404, "Expected 404 for nonexistent user ID"

# Test password reset request with mock email sending
@patch("app.routers.auth_router.create_password_reset_token")
@patch("app.services.email_service.EmailService.send_password_change_request")
async def test_password_reset_request_success(
    mock_send_email, mock_create_token, client: AsyncClient, test_user
):
    # Mock token creation
    mock_create_token.return_value = "test_reset_token"
    
    # Test with existing email
    response = await client.post(
        "/auth/password-reset-request", 
        json={"email": test_user["email"]}
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset link sent to email if account exists"
    
    # Verify mock was called with any db session and the right email
    mock_create_token.assert_called_once()
    args, _ = mock_create_token.call_args
    assert args[1] == test_user["email"]  # Check email is correct
    mock_send_email.assert_called_once()

# Test password reset request with non-existent email
@patch("app.routers.auth_router.create_password_reset_token")
@patch("app.services.email_service.EmailService.send_password_change_request")
async def test_password_reset_request_nonexistent_email(
    mock_send_email, mock_create_token, client: AsyncClient
):
    # Mock token creation to raise error
    mock_create_token.side_effect = UserNotFoundError("User not found")
    
    # Test with non-existent email
    response = await client.post(
        "/auth/password-reset-request", 
        json={"email": "nonexistent@example.com"}
    )
    
    # Should still return 200 to prevent email enumeration
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset link sent to email if account exists"
    
    # Verify send_email was not called
    mock_send_email.assert_not_called()

# Test reset password with token
@patch("app.routers.auth_router.verify_reset_token")
@patch("app.routers.auth_router.reset_password")
async def test_reset_password_with_valid_token(
    mock_reset_password, mock_verify_token, client: AsyncClient
):
    # Mock token verification
    mock_verify_token.return_value = 123  # Mock user ID
    
    # Test with valid token
    response = await client.post(
        "/auth/reset-password",
        json={"token": "valid_reset_token", "new_password": "NewSecurePassword123!"}
    )
    
    assert response.status_code == 200
    assert response.json()["message"] == "Password has been reset successfully"
    
    # Verify mocks were called with correct arguments
    mock_verify_token.assert_called_once_with("valid_reset_token")
    
    # Verify only the user_id and password parameters
    mock_reset_password.assert_called_once()
    args, _ = mock_reset_password.call_args
    assert args[1] == 123  # Check user_id is correct
    assert args[2] == "NewSecurePassword123!"  # Check password is correct

# Test reset password with invalid token
@patch("app.routers.auth_router.verify_reset_token")
async def test_reset_password_with_invalid_token(mock_verify_token, client: AsyncClient):
    # Mock token verification to raise error
    mock_verify_token.side_effect = jwt.JWTError("Invalid token")
    
    # Test with invalid token
    response = await client.post(
        "/auth/reset-password",
        json={"token": "invalid_token", "new_password": "NewSecurePassword123!"}
    )
    
    assert response.status_code == 400, "Expected 400 Bad Request for invalid token"
    # The format of the response may vary, so just check the status code