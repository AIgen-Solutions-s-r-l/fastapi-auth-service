"""Test for final balance check after multiple operations."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from app.core.config import settings

pytestmark = pytest.mark.asyncio

async def test_final_balance_check(async_client: AsyncClient, verified_test_user, db_session):
    """Test final balance after all operations."""
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
    
    # Add initial credits
    await async_client.post(
        f"/credits/add?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(Decimal("100.50")),
            "reference_id": "test_final_001",
            "description": "Initial credit for final test"
        }
    )
    
    # Use some credits
    await async_client.post(
        f"/credits/use?user_id={user_id}",
        headers=headers,
        json={
            "amount": str(Decimal("50.25")),
            "reference_id": "test_final_002",
            "description": "Use credits for final test"
        }
    )
    
    # Check final balance
    response = await async_client.get(f"/credits/balance?user_id={user_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    expected_balance = Decimal("50.25")  # 100.50 - 50.25
    assert Decimal(data["balance"]) == expected_balance, "Final balance incorrect"