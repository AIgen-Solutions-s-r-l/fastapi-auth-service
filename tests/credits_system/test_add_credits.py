"""Tests for credit addition functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_add_credits(async_client: AsyncClient, test_user):
    """Test adding credits to user's balance."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    amount = Decimal("100.50")
    
    response = await async_client.post(
        "/credits/add",
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


async def test_add_credits_invalid_amount(async_client: AsyncClient, test_user):
    """Test adding invalid credit amount."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    response = await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": "-50.00",
            "reference_id": "test_invalid_001",
            "description": "Invalid amount test"
        }
    )
    
    assert response.status_code == 422, "Should reject negative amount"