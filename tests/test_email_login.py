"""Test email-based login functionality."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.user import User
from app.services.user_service import UserService

pytestmark = pytest.mark.asyncio


async def test_login_with_email(async_client: AsyncClient, test_app: FastAPI, db_session: AsyncSession):
    """Test logging in with email and password."""
    # Create a test user
    email = "test_email_login@example.com"
    password = "testpassword"
    
    # Create user directly in the database
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    
    # Attempt to login with email and password
    response = await async_client.post(
        "/auth/login",
        json={"email": email, "password": password}
    )
    
    # Check response
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    
    # Verify token contents by using it to access a protected endpoint
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["email"] == email


async def test_login_with_invalid_email(async_client: AsyncClient, test_app: FastAPI):
    """Test login with invalid email returns appropriate error."""
    response = await async_client.post(
        "/auth/login",
        json={"email": "nonexistent@example.com", "password": "wrongpassword"}
    )
    
    assert response.status_code == 401
    assert "detail" in response.json()


async def test_login_with_wrong_password(
    async_client: AsyncClient, test_app: FastAPI, db_session: AsyncSession
):
    """Test login with correct email but wrong password."""
    # Create a test user
    email = "test_wrong_password@example.com"
    password = "testpassword"
    
    # Create user directly in the database
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    
    # Attempt to login with correct email but wrong password
    response = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "wrongpassword"}
    )
    
    assert response.status_code == 401
    assert "detail" in response.json()


async def test_email_authentication(
    async_client: AsyncClient, test_app: FastAPI, db_session: AsyncSession
):
    """
    Test that the authenticate_user function works with email.
    """
    # Create a test user
    email = "test_auth@example.com"
    password = "testpassword"
    
    # Create user directly in the database
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_verified=True
    )
    db_session.add(user)
    await db_session.commit()
    
    # Use the UserService directly to test authentication
    service = UserService(db_session)
    
    # Should be able to authenticate with email
    authenticated_user = await service.authenticate_user(
        email, password
    )
    assert authenticated_user is not None
    assert authenticated_user.email == email