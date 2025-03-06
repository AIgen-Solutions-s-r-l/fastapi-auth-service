"""Test cases for email verification functionality."""

import pytest
from datetime import datetime, timedelta, UTC
from fastapi import status
from sqlalchemy import select
from app.models.user import User, EmailVerificationToken
from app.core.security import verify_jwt_token

pytestmark = pytest.mark.asyncio

async def test_successful_verification(client, db, test_user_data):
    """Test successful email verification."""
    # Create user and verification token
    from tests.conftest import create_test_user, create_test_token
    user = await create_test_user(db, test_user_data["email"], test_user_data["password"])
    token = "test_verification_token"
    await create_test_token(db, user.id, token)
    
    # Verify email
    response = client.get(f"/auth/verify-email?token={token}")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["message"] == "Email verified successfully"
    assert data["is_verified"] is True
    assert "access_token" in data
    
    # Verify JWT token
    token = data["access_token"]
    payload = verify_jwt_token(token)
    assert payload["sub"] == test_user_data["email"]
    
    # Check database
    result = await db.execute(select(User).where(User.id == user.id))
    updated_user = result.scalar_one()
    assert updated_user.is_verified is True

async def test_verify_invalid_token(client, db):
    """Test verification with invalid token."""
    response = client.get("/auth/verify-email?token=invalid_token")
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data
    assert "message" in data["detail"]
    assert data["detail"]["message"] == "Invalid verification token"

async def test_verify_expired_token(client, db, test_user_data):
    """Test verification with expired token."""
    # Create user and expired token
    from tests.conftest import create_test_user, create_test_token
    user = await create_test_user(db, test_user_data["email"], test_user_data["password"])
    token = "test_verification_token"
    await create_test_token(db, user.id, token, expires_in_hours=-1)  # Expired 1 hour ago
    
    response = client.get(f"/auth/verify-email?token={token}")
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data
    assert "message" in data["detail"]
    assert data["detail"]["message"] == "Verification token has expired"

async def test_verify_used_token(client, db, test_user_data):
    """Test verification with already used token."""
    # Create user and token
    from tests.conftest import create_test_user, create_test_token
    user = await create_test_user(db, test_user_data["email"], test_user_data["password"])
    token = "test_verification_token"
    token_record = await create_test_token(db, user.id, token)
    
    # Use token once
    response = client.get(f"/auth/verify-email?token={token}")
    assert response.status_code == status.HTTP_200_OK
    
    # Try to use token again
    response = client.get(f"/auth/verify-email?token={token}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data
    assert "message" in data["detail"]
    assert data["detail"]["message"] == "Invalid verification token"

async def test_verify_nonexistent_user(client, db):
    """Test verification token for non-existent user."""
    # Create token with non-existent user_id
    token = "test_verification_token"
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    token_record = EmailVerificationToken(
        token=token,
        user_id=99999,  # Non-existent user ID
        expires_at=expires_at,
        used=False
    )
    db.add(token_record)
    await db.commit()
    
    response = client.get(f"/auth/verify-email?token={token}")
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data
    assert "message" in data["detail"]
    assert data["detail"]["message"] == "Invalid verification token"

async def test_verify_missing_token(client):
    """Test verification without token."""
    response = client.get("/auth/verify-email")
    
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert "details" in data
    errors = data["details"]
    assert any("token" in error["loc"] for error in errors)

async def test_verify_empty_token(client):
    """Test verification with empty token."""
    response = client.get("/auth/verify-email?token=")
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "detail" in data
    assert "message" in data["detail"]
    assert data["detail"]["message"] == "Invalid verification token"

async def test_verify_welcome_email(client, db, test_user_data, mock_email_service):
    """Test that verification triggers welcome email."""
    # Create user and token
    from tests.conftest import create_test_user, create_test_token
    user = await create_test_user(db, test_user_data["email"], test_user_data["password"])
    token = "test_verification_token"
    await create_test_token(db, user.id, token)
    
    # Verify email
    response = client.get(f"/auth/verify-email?token={token}")
    
    assert response.status_code == status.HTTP_200_OK
    
    # Verify welcome email was sent
    assert mock_email_service["welcome"].called
    call_args = mock_email_service["welcome"].call_args
    assert call_args is not None
    args, kwargs = call_args
    assert len(args) == 1
    assert isinstance(args[0], User)
    assert args[0].email == test_user_data["email"]

async def test_verify_already_verified(client, db, test_user_data):
    """Test verification when user is already verified."""
    # Create verified user and token
    from tests.conftest import create_test_user, create_test_token
    user = await create_test_user(db, test_user_data["email"], test_user_data["password"], is_verified=True)
    token = "test_verification_token"
    await create_test_token(db, user.id, token)
    
    response = client.get(f"/auth/verify-email?token={token}")
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_verified"] is True
    assert "access_token" in data