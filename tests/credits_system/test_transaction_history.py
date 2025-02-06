"""Tests for transaction history functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_get_transaction_history(async_client: AsyncClient, test_user):
    """Test retrieving transaction history."""
    # First create some transactions
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Add credits
    await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": str(Decimal("100.00")),
            "reference_id": "test_history_001",
            "description": "Add credits for history test"
        }
    )
    
    # Use credits
    await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": str(Decimal("50.00")),
            "reference_id": "test_history_002",
            "description": "Use credits for history test"
        }
    )
    
    # Get history
    response = await async_client.get("/credits/transactions", headers=headers)
    
    assert response.status_code == 200, f"Get transactions failed with status {response.status_code}"
    data = response.json()
    assert "transactions" in data, "Transactions not found in response"
    assert "total_count" in data, "Total count not found in response"
    assert data["total_count"] >= 2, "Should have at least 2 transactions"
    
    # Verify transaction details
    transactions = data["transactions"]
    assert any(t["transaction_type"] == "credit_added" for t in transactions), "Add transaction not found"
    assert any(t["transaction_type"] == "credit_used" for t in transactions), "Use transaction not found"

async def test_get_transaction_history_pagination(async_client: AsyncClient, test_user):
    """Test transaction history pagination."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Create multiple transactions
    for i in range(3):
        await async_client.post(
            "/credits/add",
            headers=headers,
            json={
                "amount": str(Decimal("10.00")),
                "reference_id": f"test_pagination_{i}",
                "description": f"Transaction {i} for pagination test"
            }
        )
    
    # Test with limit
    response = await async_client.get("/credits/transactions?limit=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["transactions"]) == 1, "Limit parameter not respected"
    
    # Test with skip
    response = await async_client.get("/credits/transactions?skip=1&limit=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["transactions"]) == 1, "Skip parameter not respected"