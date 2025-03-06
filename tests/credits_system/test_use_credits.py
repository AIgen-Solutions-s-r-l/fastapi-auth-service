"""Tests for using credits functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from app.core.config import settings

pytestmark = pytest.mark.asyncio

async def test_use_credits(async_client: AsyncClient, verified_test_user, db_session):
    """Test using credits from user's balance."""
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
    
    # First add credits
    add_amount = Decimal("100.50")
    await async_client.post(
        f"/credits/add?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(add_amount),
            "reference_id": "test_add_002",
            "description": "Add credits for usage test"
        }
    )
    
    # Then use credits
    use_amount = Decimal("50.25")
    response = await async_client.post(
        f"/credits/use?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(use_amount),
            "reference_id": "test_use_001",
            "description": "Test credit usage"
        }
    )
    
    assert response.status_code == 200, f"Use credits failed with status {response.status_code}"
    data = response.json()
    assert Decimal(data["amount"]) == use_amount, "Used amount doesn't match"
    assert data["transaction_type"] == "credit_used", "Wrong transaction type"
    assert Decimal(data["new_balance"]) == add_amount - use_amount, "New balance incorrect after usage"

async def test_use_credits_insufficient_balance(async_client: AsyncClient, verified_test_user, db_session):
    """Test using more credits than available."""
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
        f"/credits/use?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(Decimal("1000.00")),
            "reference_id": "test_insufficient_001",
            "description": "Attempt to use more than available"
        }
    )
    
    assert response.status_code == 400, "Should reject insufficient balance"
    error_message = response.json()
    assert "insufficient" in str(error_message).lower(), "Wrong error message"