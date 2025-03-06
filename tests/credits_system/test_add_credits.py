"""Tests for credit addition functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def test_add_credits(async_client: AsyncClient, verified_test_user, db_session):
    """Test adding credits to user's balance."""
    # Get user ID from the test user
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db_session.execute(select(User).where(User.email == verified_test_user["email"]))
    user = result.scalar_one_or_none()
    user_id = user.id
    
    # Setup headers with API key
    headers = {
        "api-key": settings.INTERNAL_API_KEY
    }
    
    amount = Decimal("100.50")
    
    response = await async_client.post(
        f"/credits/add?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(amount),  # Convert Decimal to string for JSON serialization
            "reference_id": "test_add_001",
            "description": "Test credit addition"
        }
    )
    
    assert response.status_code == 200, f"Add credits failed with status {response.status_code}"
    data = response.json()
    assert Decimal(data["amount"]) == amount, "Added amount doesn't match"
    assert data["transaction_type"] == "credit_added", "Wrong transaction type"
    assert Decimal(data["new_balance"]) == amount, "New balance incorrect"


async def test_add_credits_invalid_amount(async_client: AsyncClient, verified_test_user, db_session):
    """Test adding invalid credit amount."""
    # Get user ID from the test user
    from sqlalchemy import select
    from app.models.user import User
    
    result = await db_session.execute(select(User).where(User.email == verified_test_user["email"]))
    user = result.scalar_one_or_none()
    user_id = user.id
    
    # Setup headers with API key
    headers = {
        "api-key": settings.INTERNAL_API_KEY
    }
    
    response = await async_client.post(
        f"/credits/add?user_id={user_id}",
        headers=headers,
        json={
            "amount": "-50.00",
            "reference_id": "test_invalid_001",
            "description": "Invalid amount test"
        }
    )
    
    assert response.status_code == 422, "Should reject negative amount"