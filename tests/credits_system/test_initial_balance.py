"""Test for getting initial credit balance."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_get_initial_balance(async_client: AsyncClient, test_user):
    """Test getting initial credit balance."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await async_client.get("/credits/balance", headers=headers)
    
    assert response.status_code == 200, f"Get balance failed with status {response.status_code}"
    data = response.json()
    assert "balance" in data, "Balance not found in response"
    assert data["balance"] == 0, "Initial balance should be 0"