"""Basic tests for the authentication router."""

import pytest
from fastapi import status
from jose import jwt
from app.core.config import settings

pytestmark = pytest.mark.asyncio

async def test_login_success(client, test_user):
    """Test successful login."""
    response = await client.post( # Added await
        "/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # Verify token contains expected claims
    token = data["access_token"]
    payload = jwt.decode(
        token, 
        settings.secret_key, 
        algorithms=[settings.algorithm]
    )
    assert payload["sub"] == test_user["email"]
    assert "id" in payload
    assert "is_admin" in payload
    assert "exp" in payload

async def test_login_invalid_credentials(client, test_user):
    """Test login with invalid credentials."""
    response = await client.post( # Added await
        "/auth/login",
        json={"email": test_user["email"], "password": "wrong_password"}
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    data = response.json()
    assert "detail" in data

async def test_register_success(client):
    """Test successful user registration."""
    response = await client.post( # Added await
        "/auth/register",
        json={"email": "newuser@example.com", "password": "password123"}
    )
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["verification_sent"] is True
    assert "message" in data

async def test_register_duplicate_email(client, test_user):
    """Test registration with existing email."""
    # First registration already done in fixture
    # Attempt duplicate registration
    response = await client.post( # Added await
        "/auth/register",
        json={"email": test_user["email"], "password": "password123"}
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data

async def test_register_invalid_email(client):
    """Test registration with invalid email format."""
    response = await client.post( # Added await
        "/auth/register",
        json={"email": "invalid-email", "password": "password123"}
    )
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert "details" in data
    errors = data["details"]
    assert any("email" in error["loc"] for error in errors)

async def test_register_weak_password(client):
    """Test registration with weak password."""
    response = await client.post( # Added await
        "/auth/register",
        json={"email": "test@example.com", "password": "short"}
    )
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert "details" in data
    errors = data["details"]
    assert any("password" in error["loc"] for error in errors)

async def test_get_current_user_profile(client, test_user_token):
    """Test retrieving the current user's profile."""
    response = await client.get( # Added await
        "/auth/me",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "email" in data
    assert "is_verified" in data

async def test_refresh_token(client, test_user_token):
    """Test refreshing a JWT token."""
    response = await client.post( # Added await
        "/auth/refresh",
        json={"token": test_user_token}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # Verify new token is valid
    token = data["access_token"]
    payload = jwt.decode(
        token, 
        settings.secret_key, 
        algorithms=[settings.algorithm]
    )
    assert "sub" in payload
    assert "id" in payload
    assert "is_admin" in payload
    assert "exp" in payload

async def test_logout(client, test_user_token):
    """Test user logout."""
    response = await client.post( # Added await
        "/auth/logout",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "message" in data
    assert data["message"] == "Successfully logged out"