"""Test for final balance check after multiple operations."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_final_balance_check(async_client: AsyncClient, test_user):
    """Test final balance after all operations."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Add initial credits
    await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": str(Decimal("100.50")),
            "reference_id": "test_final_001",
            "description": "Initial credit for final test"
        }
    )
    
    # Use some credits
    await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": str(Decimal("50.25")),
            "reference_id": "test_final_002",
            "description": "Use credits for final test"
        }
    )
    
    # Check final balance
    response = await async_client.get("/credits/balance", headers=headers)
    assert response.status_code == 200
    data = response.json()
    expected_balance = Decimal("50.25")  # 100.50 - 50.25
    assert Decimal(data["balance"]) == expected_balance, "Final balance incorrect"