"""Tests for the refactored CreditService."""

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, UTC, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks

from app.models.user import User
from app.models.plan import Plan, Subscription
from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.services.credit import CreditService, InsufficientCreditsError
from app.schemas import credit_schemas

# Mock EmailService for testing
class MockEmailService:
    async def send_payment_confirmation(self, *args, **kwargs):
        pass
    async def send_plan_upgrade(self, *args, **kwargs):
        pass
    async def send_one_time_credit_purchase(self, *args, **kwargs):
        pass

@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Fixture for creating a test user."""
    user = User(
        email="test@example.com",
        hashed_password="password",
        is_admin=False,  # Using correct fields from the User model
        is_verified=True,
        auth_type="password"  # Required field
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@pytest_asyncio.fixture
async def test_plan(db: AsyncSession) -> Plan:
    """Fixture for creating a test plan."""
    plan = Plan(
        name="Test Plan",
        credit_amount=Decimal("100.00"),
        price=Decimal("10.00"),
        is_active=True
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

@pytest_asyncio.fixture
async def credit_service(db: AsyncSession) -> CreditService:
    """Fixture for creating a CreditService instance."""
    service = CreditService(db)
    # Inject mock email service if needed, or handle background tasks
    # For simplicity, we'll assume background tasks are handled elsewhere or mocked
    return service

@pytest.mark.asyncio
async def test_get_user_credit_new(credit_service: CreditService, test_user: User):
    """Test getting credit record for a new user."""
    credit = await credit_service.get_user_credit(test_user.id)
    assert credit is not None
    assert credit.user_id == test_user.id
    assert credit.balance == Decimal("0.00")

@pytest.mark.asyncio
async def test_get_user_credit_existing(credit_service: CreditService, test_user: User):
    """Test getting credit record for an existing user."""
    # Create initial record
    await credit_service.get_user_credit(test_user.id)
    # Get again
    credit = await credit_service.get_user_credit(test_user.id)
    assert credit is not None
    assert credit.user_id == test_user.id
    assert credit.balance == Decimal("0.00")

@pytest.mark.asyncio
async def test_add_credits(credit_service: CreditService, test_user: User):
    """Test adding credits."""
    amount_to_add = Decimal("50.00")
    transaction = await credit_service.add_credits(
        user_id=test_user.id,
        amount=amount_to_add,
        description="Test credit addition"
    )
    
    assert transaction is not None
    assert transaction.user_id == test_user.id
    assert transaction.amount == amount_to_add
    assert transaction.transaction_type == TransactionType.CREDIT_ADDED
    assert transaction.new_balance == amount_to_add
    
    credit = await credit_service.get_user_credit(test_user.id)
    assert credit.balance == amount_to_add

@pytest.mark.asyncio
async def test_use_credits_sufficient(credit_service: CreditService, test_user: User):
    """Test using credits when balance is sufficient."""
    initial_amount = Decimal("100.00")
    await credit_service.add_credits(user_id=test_user.id, amount=initial_amount)
    
    amount_to_use = Decimal("30.00")
    transaction = await credit_service.use_credits(
        user_id=test_user.id,
        amount=amount_to_use,
        description="Test credit usage"
    )
    
    expected_balance = initial_amount - amount_to_use
    assert transaction is not None
    assert transaction.user_id == test_user.id
    assert transaction.amount == amount_to_use
    assert transaction.transaction_type == TransactionType.CREDIT_USED
    assert transaction.new_balance == expected_balance
    
    credit = await credit_service.get_user_credit(test_user.id)
    assert credit.balance == expected_balance

@pytest.mark.asyncio
async def test_use_credits_insufficient(credit_service: CreditService, test_user: User):
    """Test using credits when balance is insufficient."""
    initial_amount = Decimal("20.00")
    await credit_service.add_credits(user_id=test_user.id, amount=initial_amount)
    
    # Get the balance before attempting to use credits
    credit_before = await credit_service.get_user_credit(test_user.id)
    assert credit_before.balance == initial_amount
    
    amount_to_use = Decimal("30.00")
    with pytest.raises(Exception) as excinfo:
        await credit_service.use_credits(
            user_id=test_user.id,
            amount=amount_to_use
        )
    
    # Check that the exception message contains the expected text
    assert "Insufficient credits" in str(excinfo.value)

@pytest.mark.asyncio
async def test_get_balance(credit_service: CreditService, test_user: User):
    """Test getting the credit balance."""
    amount = Decimal("75.50")
    await credit_service.add_credits(user_id=test_user.id, amount=amount)
    
    balance_response = await credit_service.get_balance(test_user.id)
    assert balance_response.user_id == test_user.id
    assert balance_response.balance == amount
    assert isinstance(balance_response.updated_at, datetime)

@pytest.mark.asyncio
async def test_get_transaction_history(credit_service: CreditService, test_user: User):
    """Test getting transaction history."""
    await credit_service.add_credits(user_id=test_user.id, amount=Decimal("10.00"), description="Tx 1")
    await credit_service.use_credits(user_id=test_user.id, amount=Decimal("5.00"), description="Tx 2")
    await credit_service.add_credits(user_id=test_user.id, amount=Decimal("20.00"), description="Tx 3")
    
    history = await credit_service.get_transaction_history(user_id=test_user.id, limit=10)
    
    assert history.total_count == 3
    assert len(history.transactions) == 3
    
    # Transactions should be ordered by created_at desc
    assert history.transactions[0].description == "Tx 3"
    assert history.transactions[1].description == "Tx 2"
    assert history.transactions[2].description == "Tx 1"
    
    # Check current balance attached to each transaction
    final_balance = Decimal("10.00") - Decimal("5.00") + Decimal("20.00")
    for tx in history.transactions:
        assert tx.new_balance == final_balance

@pytest.mark.asyncio
async def test_purchase_plan(credit_service: CreditService, test_user: User, test_plan: Plan, db: AsyncSession):
    """Test purchasing a plan."""
    # Mock background tasks
    background_tasks = BackgroundTasks()
    
    transaction, subscription = await credit_service.purchase_plan(
        user_id=test_user.id,
        plan_id=test_plan.id,
        description="Test plan purchase",
        background_tasks=background_tasks # Pass mock tasks
    )
    
    assert transaction is not None
    assert transaction.user_id == test_user.id
    assert transaction.amount == test_plan.credit_amount
    assert transaction.transaction_type == TransactionType.PLAN_PURCHASE
    assert transaction.plan_id == test_plan.id
    assert transaction.subscription_id == subscription.id
    
    assert subscription is not None
    assert subscription.user_id == test_user.id
    assert subscription.plan_id == test_plan.id
    assert subscription.is_active is True
    assert subscription.auto_renew is True
    
    credit = await credit_service.get_user_credit(test_user.id)
    assert credit.balance == test_plan.credit_amount

# Add more tests for renew_subscription, upgrade_plan, etc.
# Remember to handle mocking/setup for dependencies like StripeService if needed.