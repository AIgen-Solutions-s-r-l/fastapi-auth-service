"""Tests for using credits functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_use_credits(async_client: AsyncClient, test_user):
    """Test using credits from user's balance."""
    # First add credits
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    add_amount = Decimal("100.50")
    await async_client.post(
        "/credits/add",
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
        "/credits/use",
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

async def test_use_credits_insufficient_balance(async_client: AsyncClient, test_user):
    """Test using more credits than available."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await async_client.post(
        "/credits/use",
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