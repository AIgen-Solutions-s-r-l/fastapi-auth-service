"""Tests for unauthorized access to credit endpoints."""

import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_missing_api_key(async_client: AsyncClient):
    """Test accessing endpoints without API key."""
    endpoints = [
        ("GET", "/credits/balance?user_id=1"),
        ("POST", "/credits/add?user_id=1"),
        ("POST", "/credits/use?user_id=1"),
        ("GET", "/credits/transactions?user_id=1")
    ]
    
    for method, endpoint in endpoints:
        if method == "GET":
            response = await async_client.get(endpoint)
        else:
            response = await async_client.post(endpoint, json={
                "amount": str(Decimal("100.00")),
                "reference_id": "test_unauth_001"
            })
        
        # API key is required, should get a 422 validation error
        assert response.status_code == 422, f"{method} {endpoint} should require API key"
        assert "api-key" in response.text.lower(), "Error should mention api-key requirement"

async def test_invalid_api_key(async_client: AsyncClient):
    """Test accessing endpoints with invalid API key."""
    endpoints = [
        ("GET", "/credits/balance?user_id=1"),
        ("POST", "/credits/add?user_id=1"),
        ("POST", "/credits/use?user_id=1"),
        ("GET", "/credits/transactions?user_id=1")
    ]
    
    headers = {"api-key": "invalid_key_value"}
    
    for method, endpoint in endpoints:
        if method == "GET":
            response = await async_client.get(endpoint, headers=headers)
        else:
            response = await async_client.post(
                endpoint,
                headers=headers,
                json={
                    "amount": str(Decimal("100.00")),
                    "reference_id": "test_unauth_002"
                }
            )
        
        # Invalid API key should get a 403 Forbidden
        assert response.status_code == 403, f"{method} {endpoint} should reject invalid API key"
        
async def test_missing_user_id(async_client: AsyncClient):
    """Test accessing endpoints without user_id parameter."""
    from app.core.config import settings
    
    endpoints = [
        ("GET", "/credits/balance"),
        ("POST", "/credits/add"),
        ("POST", "/credits/use"),
        ("GET", "/credits/transactions")
    ]
    
    headers = {"api-key": settings.INTERNAL_API_KEY}
    
    for method, endpoint in endpoints:
        if method == "GET":
            response = await async_client.get(endpoint, headers=headers)
        else:
            response = await async_client.post(
                endpoint,
                headers=headers,
                json={
                    "amount": str(Decimal("100.00")),
                    "reference_id": "test_unauth_003"
                }
            )
        
        # Missing user_id should get a 422 validation error
        assert response.status_code == 422, f"{method} {endpoint} should require user_id"
        assert "user_id" in response.text.lower(), "Error should mention user_id requirement"