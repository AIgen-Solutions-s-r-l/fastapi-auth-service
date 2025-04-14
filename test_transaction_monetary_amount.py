"""Test for transaction monetary amount feature."""

import pytest
from decimal import Decimal
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.credit_service import CreditService
from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_transaction_monetary_amount(
    client: AsyncClient,
    app: FastAPI,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict
):
    """Test that transaction history includes monetary amounts."""
    # Setup
    user_service = UserService(db_session)
    credit_service = CreditService(db_session)
    
    # Add credits with monetary amount
    credit_amount = Decimal("100.00")
    monetary_amount = Decimal("39.99")
    
    # Add credits directly using the service
    await credit_service.add_credits(
        user_id=test_user.id,
        amount=credit_amount,
        reference_id="test-ref-123",
        description="Test transaction with monetary amount",
        monetary_amount=monetary_amount
    )
    
    # Get transaction history
    response = await client.get(
        f"/credits/user/transactions",
        headers=auth_headers
    )
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    
    # Check that transactions are returned
    assert "transactions" in data
    assert len(data["transactions"]) > 0
    
    # Find our test transaction
    test_transaction = None
    for tx in data["transactions"]:
        if tx["reference_id"] == "test-ref-123":
            test_transaction = tx
            break
    
    assert test_transaction is not None
    
    # Verify monetary amount is included
    assert "monetary_amount" in test_transaction
    assert test_transaction["monetary_amount"] == str(monetary_amount)
    
    # Verify currency is included
    assert "currency" in test_transaction
    assert test_transaction["currency"] == "USD"
    
    # Verify other transaction details
    assert test_transaction["amount"] == str(credit_amount)
    assert test_transaction["description"] == "Test transaction with monetary amount"