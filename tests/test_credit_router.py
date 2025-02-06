"""Tests for credit-related endpoints."""

import uuid
import pytest
from decimal import Decimal
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="function")
async def test_user(async_client: AsyncClient):
    """Create a test user for credit operations."""
    # Generate a unique username and email
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"
    
    # Register the user
    response = await async_client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    if response.status_code != 201:
        pytest.skip("Registration failed, skipping credit router tests")
    data = response.json()
    token = data.get("access_token")
    user_data = {"username": username, "email": email, "password": password, "token": token}
    
    yield user_data
    
    # Cleanup: delete the user after tests run
    await async_client.delete(
        f"/auth/users/{username}",
        params={"password": password},
        headers={"Authorization": f"Bearer {token}"}
    )

async def test_get_initial_balance(async_client: AsyncClient, test_user):
    """Test getting initial credit balance."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    response = await async_client.get("/credits/balance", headers=headers)
    
    assert response.status_code == 200, f"Get balance failed with status {response.status_code}"
    data = response.json()
    assert "balance" in data, "Balance not found in response"
    assert data["balance"] == 0, "Initial balance should be 0"

async def test_add_credits(async_client: AsyncClient, test_user):
    """Test adding credits to user's balance."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    amount = 100.50
    
    response = await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": amount,
            "reference_id": "test_add_001",
            "description": "Test credit addition"
        }
    )
    
    assert response.status_code == 200, f"Add credits failed with status {response.status_code}"
    data = response.json()
    assert data["amount"] == amount, "Added amount doesn't match"
    assert data["transaction_type"] == "credit_added", "Wrong transaction type"
    assert data["new_balance"] == amount, "New balance incorrect"

async def test_add_credits_invalid_amount(async_client: AsyncClient, test_user):
    """Test adding invalid credit amount."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    response = await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": -50.00,
            "description": "Invalid amount test"
        }
    )
    
    assert response.status_code == 422, "Should reject negative amount"

async def test_use_credits(async_client: AsyncClient, test_user):
    """Test using credits from user's balance."""
    # First add credits
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    add_amount = 100.50
    await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": add_amount,
            "reference_id": "test_add_002",
            "description": "Add credits for usage test"
        }
    )
    
    # Then use credits
    use_amount = 50.25
    response = await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": use_amount,
            "reference_id": "test_use_001",
            "description": "Test credit usage"
        }
    )
    
    assert response.status_code == 200, f"Use credits failed with status {response.status_code}"
    data = response.json()
    assert data["amount"] == use_amount, "Used amount doesn't match"
    assert data["transaction_type"] == "credit_used", "Wrong transaction type"
    assert data["new_balance"] == 50.25, "New balance incorrect after usage"  # 100.50 - 50.25

async def test_use_credits_insufficient_balance(async_client: AsyncClient, test_user):
    """Test using more credits than available."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    response = await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": 1000.00,
            "description": "Attempt to use more than available"
        }
    )
    
    assert response.status_code == 400, "Should reject insufficient balance"
    assert "insufficient" in response.json()["detail"].lower(), "Wrong error message"

async def test_get_transaction_history(async_client: AsyncClient, test_user):
    """Test retrieving transaction history."""
    # First create some transactions
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Add credits
    await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": 100.00,
            "reference_id": "test_history_001",
            "description": "Add credits for history test"
        }
    )
    
    # Use credits
    await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": 50.00,
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
                "amount": 10.00,
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
            response = await async_client.post(endpoint, json={"amount": 100})
        
        assert response.status_code == 401, f"{method} {endpoint} should require authentication"

async def test_final_balance_check(async_client: AsyncClient, test_user):
    """Test final balance after all operations."""
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Add initial credits
    await async_client.post(
        "/credits/add",
        headers=headers,
        json={
            "amount": 100.50,
            "reference_id": "test_final_001",
            "description": "Initial credit for final test"
        }
    )
    
    # Use some credits
    await async_client.post(
        "/credits/use",
        headers=headers,
        json={
            "amount": 50.25,
            "reference_id": "test_final_002",
            "description": "Use credits for final test"
        }
    )
    
    # Check final balance
    response = await async_client.get("/credits/balance", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 50.25, "Final balance incorrect"  # 100.50 - 50.25