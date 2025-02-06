"""Tests for unauthorized access to credit endpoints."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_unauthorized_access(async_client: AsyncClient):
    """Test accessing endpoints without authentication."""
    endpoints = [
        ("GET", "/credits/balance"),
        ("POST", "/credits/add"),
        ("POST", "/credits/use"),
        ("GET", "/credits/transactions")
    ]
    
    for method, endpoint in endpoints:
        if method == "GET":
            response = await async_client.get(endpoint)
        else:
            response = await async_client.post(endpoint, json={
                "amount": str(Decimal("100.00")),
                "reference_id": "test_unauth_001"
            })
        
        assert response.status_code == 401, f"{method} {endpoint} should require authentication"