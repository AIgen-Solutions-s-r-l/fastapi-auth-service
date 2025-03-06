"""Test for getting initial credit balance."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from app.core.config import settings

pytestmark = pytest.mark.asyncio

async def test_get_initial_balance(async_client: AsyncClient, verified_test_user, db_session):
    """Test getting initial credit balance."""
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
    
    response = await async_client.get(f"/credits/balance?user_id={user_id}", headers=headers)
    
    assert response.status_code == 200, f"Get balance failed with status {response.status_code}"
    data = response.json()
    assert "balance" in data, "Balance not found in response"
    assert Decimal(data["balance"]) == Decimal("0.00"), "Initial balance should be 0.00"