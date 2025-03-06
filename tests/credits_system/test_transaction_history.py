"""Tests for transaction history functionality."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from app.core.config import settings

pytestmark = pytest.mark.asyncio

async def test_get_transaction_history(async_client: AsyncClient, verified_test_user, db_session):
    """Test retrieving transaction history."""
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
    
    # Add credits
    await async_client.post(
        f"/credits/add?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(Decimal("100.00")),
            "reference_id": "test_history_001",
            "description": "Add credits for history test"
        }
    )
    
    # Use credits
    await async_client.post(
        f"/credits/use?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(Decimal("50.00")),
            "reference_id": "test_history_002",
            "description": "Use credits for history test"
        }
    )
    
    # Get history
    response = await async_client.get(f"/credits/transactions?user_id={user_id}", headers=headers)
    
    assert response.status_code == 200, f"Get transactions failed with status {response.status_code}"
    data = response.json()
    assert "transactions" in data, "Transactions not found in response"
    assert "total_count" in data, "Total count not found in response"
    assert data["total_count"] >= 2, "Should have at least 2 transactions"
    
    # Verify transaction details
    transactions = data["transactions"]
    assert any(t["transaction_type"] == "credit_added" for t in transactions), "Add transaction not found"
    assert any(t["transaction_type"] == "credit_used" for t in transactions), "Use transaction not found"

async def test_get_transaction_history_pagination(async_client: AsyncClient, verified_test_user, db_session):
    """Test transaction history pagination."""
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
    
    # Create multiple transactions
    for i in range(3):
        await async_client.post(
            f"/credits/add?user_id={user_id}",
            headers=headers,
            json={
                "amount": str(Decimal("10.00")),
                "reference_id": f"test_pagination_{i}",
                "description": f"Transaction {i} for pagination test"
            }
        )
    
    # Test with limit
    response = await async_client.get(f"/credits/transactions?user_id={user_id}&limit=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["transactions"]) == 1, "Limit parameter not respected"
    
    # Test with skip
    response = await async_client.get(f"/credits/transactions?user_id={user_id}&skip=1&limit=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["transactions"]) == 1, "Skip parameter not respected"