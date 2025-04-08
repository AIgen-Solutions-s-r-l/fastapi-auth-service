"""Tests for the refactored CreditService."""

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import BackgroundTasks, HTTPException

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
        auth_type="password",  # Required field
        stripe_customer_id="cus_test123"  # Add Stripe customer ID for testing
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
        is_active=True,
        stripe_price_id="price_test123"  # Add Stripe price ID for testing
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

@pytest_asyncio.fixture
async def test_subscription(db: AsyncSession, test_user: User, test_plan: Plan) -> Subscription:
    """Fixture for creating a test subscription."""
    start_date = datetime.now(UTC)
    renewal_date = start_date + timedelta(days=30)
    
    subscription = Subscription(
        user_id=test_user.id,
        plan_id=test_plan.id,
        start_date=start_date,
        renewal_date=renewal_date,
        is_active=True,
        auto_renew=True,
        stripe_subscription_id="sub_test123",
        status="active"
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription

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

@pytest.mark.asyncio
async def test_verify_and_process_one_time_payment_success(credit_service: CreditService, test_user: User):
    """Test verifying and processing a one-time payment successfully."""
    # Mock the verify_transaction_id method to return a successful verification
    with patch.object(credit_service.stripe_service, 'verify_transaction_id', new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "verified": True,
            "id": "pi_test123",
            "object_type": "payment_intent",
            "amount": Decimal("20.00"),
            "customer_id": "cus_test123",
            "status": "succeeded"
        }
        
        # Mock the _check_transaction_exists method to return False (transaction not processed yet)
        with patch.object(credit_service.transaction_service, '_check_transaction_exists', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = False
            
            # Mock the _calculate_credits_for_payment method to return a credit amount
            with patch.object(credit_service.transaction_service, '_calculate_credits_for_payment', new_callable=AsyncMock) as mock_calc:
                mock_calc.return_value = Decimal("200.00")  # 10x the payment amount
                
                # Execute the method
                background_tasks = BackgroundTasks()
                transaction = await credit_service.verify_and_process_one_time_payment(
                    user_id=test_user.id,
                    transaction_id="pi_test123",
                    background_tasks=background_tasks
                )
                
                # Verify the result
                assert transaction is not None
                assert transaction.user_id == test_user.id
                assert transaction.amount == Decimal("200.00")
                assert transaction.transaction_type == TransactionType.ONE_TIME_PURCHASE
                assert transaction.reference_id == "pi_test123"
                
                # Verify the user's credit balance was updated
                credit = await credit_service.get_user_credit(test_user.id)
                assert credit.balance == Decimal("200.00")
                
                # Verify the mocks were called correctly
                mock_verify.assert_called_once_with("pi_test123")
                mock_check.assert_called_once_with("pi_test123")
                mock_calc.assert_called_once_with(Decimal("20.00"))

@pytest.mark.asyncio
async def test_verify_and_process_one_time_payment_already_processed(credit_service: CreditService, test_user: User):
    """Test verifying a one-time payment that has already been processed."""
    # Mock the verify_transaction_id method to return a successful verification
    with patch.object(credit_service.stripe_service, 'verify_transaction_id', new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "verified": True,
            "id": "pi_test123",
            "object_type": "payment_intent",
            "amount": Decimal("20.00"),
            "customer_id": "cus_test123",
            "status": "succeeded"
        }
        
        # Mock the _check_transaction_exists method to return True (transaction already processed)
        with patch.object(credit_service.transaction_service, '_check_transaction_exists', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = True
            
            # Execute the method and expect an exception
            background_tasks = BackgroundTasks()
            with pytest.raises(HTTPException) as excinfo:
                await credit_service.verify_and_process_one_time_payment(
                    user_id=test_user.id,
                    transaction_id="pi_test123",
                    background_tasks=background_tasks
                )
            
            # Verify the exception details
            assert excinfo.value.status_code == 400
            assert "already been processed" in str(excinfo.value.detail)
            
            # Verify the mocks were called correctly
            mock_verify.assert_called_once_with("pi_test123")
            mock_check.assert_called_once_with("pi_test123")

@pytest.mark.asyncio
async def test_verify_and_process_one_time_payment_verification_failed(credit_service: CreditService, test_user: User):
    """Test verifying a one-time payment that fails verification."""
    # Mock the verify_transaction_id method to return a failed verification
    with patch.object(credit_service.stripe_service, 'verify_transaction_id', new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "verified": False,
            "reason": "Transaction not found or not in a valid state"
        }
        
        # Execute the method and expect an exception
        background_tasks = BackgroundTasks()
        with pytest.raises(HTTPException) as excinfo:
            await credit_service.verify_and_process_one_time_payment(
                user_id=test_user.id,
                transaction_id="pi_test123",
                background_tasks=background_tasks
            )
        
        # Verify the exception details
        assert excinfo.value.status_code == 400
        assert "Transaction verification failed" in str(excinfo.value.detail)
        
        # Verify the mock was called correctly
        mock_verify.assert_called_once_with("pi_test123")

@pytest.mark.asyncio
async def test_verify_and_process_subscription_success(credit_service: CreditService, test_user: User, test_plan: Plan):
    """Test verifying and processing a subscription successfully."""
    # Mock the verify_transaction_id method to return a successful verification
    with patch.object(credit_service.stripe_service, 'verify_transaction_id', new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "verified": True,
            "id": "sub_test123",
            "object_type": "subscription",
            "amount": Decimal("10.00"),
            "customer_id": "cus_test123",
            "status": "active",
            "plan_id": "price_test123",
            "current_period_end": datetime.now(UTC) + timedelta(days=30)
        }
        
        # Mock the check_active_subscription method to return None (no active subscription)
        with patch.object(credit_service.stripe_service, 'check_active_subscription', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = None
            
            # Mock the _find_matching_plan method to return the test plan ID
            with patch.object(credit_service.transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
                mock_find.return_value = test_plan.id
                
                # Mock the verify_subscription_active method to return True
                with patch.object(credit_service.stripe_service, 'verify_subscription_active', new_callable=AsyncMock) as mock_active:
                    mock_active.return_value = True
                    
                    # Execute the method
                    background_tasks = BackgroundTasks()
                    transaction, subscription = await credit_service.verify_and_process_subscription(
                        user_id=test_user.id,
                        transaction_id="sub_test123",
                        background_tasks=background_tasks
                    )
                    
                    # Verify the result
                    assert transaction is not None
                    assert transaction.user_id == test_user.id
                    assert transaction.amount == test_plan.credit_amount
                    assert transaction.transaction_type == TransactionType.PLAN_PURCHASE
                    assert transaction.plan_id == test_plan.id
                    
                    assert subscription is not None
                    assert subscription.user_id == test_user.id
                    assert subscription.plan_id == test_plan.id
                    assert subscription.is_active is True
                    assert subscription.stripe_subscription_id == "sub_test123"
                    
                    # Verify the user's credit balance was updated
                    credit = await credit_service.get_user_credit(test_user.id)
                    assert credit.balance == test_plan.credit_amount
                    
                    # Verify the mocks were called correctly
                    mock_verify.assert_called_once_with("sub_test123")
                    mock_check.assert_called_once_with(test_user.id)
                    mock_find.assert_called_once_with("price_test123")
                    mock_active.assert_called_once_with("sub_test123")

@pytest.mark.asyncio
async def test_verify_and_process_subscription_with_existing_subscription(credit_service: CreditService, test_user: User, test_plan: Plan, test_subscription: Subscription):
    """Test verifying and processing a subscription when user already has an active subscription."""
    # Mock the verify_transaction_id method to return a successful verification
    with patch.object(credit_service.stripe_service, 'verify_transaction_id', new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = {
            "verified": True,
            "id": "sub_new123",
            "object_type": "subscription",
            "amount": Decimal("10.00"),
            "customer_id": "cus_test123",
            "status": "active",
            "plan_id": "price_test123",
            "current_period_end": datetime.now(UTC) + timedelta(days=30)
        }
        
        # Mock the check_active_subscription method to return the existing subscription
        with patch.object(credit_service.stripe_service, 'check_active_subscription', new_callable=AsyncMock) as mock_check:
            mock_check.return_value = {
                "subscription_id": test_subscription.id,
                "stripe_subscription_id": test_subscription.stripe_subscription_id,
                "plan_id": test_subscription.plan_id,
                "stripe_plan_id": "price_test123",
                "status": "active",
                "amount": Decimal("10.00"),
                "current_period_end": datetime.now(UTC) + timedelta(days=30)
            }
            
            # Mock the cancel_subscription method to return True
            with patch.object(credit_service.stripe_service, 'cancel_subscription', new_callable=AsyncMock) as mock_cancel:
                mock_cancel.return_value = True
                
                # Mock the _find_matching_plan method to return the test plan ID
                with patch.object(credit_service.transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
                    mock_find.return_value = test_plan.id
                    
                    # Mock the verify_subscription_active method to return True
                    with patch.object(credit_service.stripe_service, 'verify_subscription_active', new_callable=AsyncMock) as mock_active:
                        mock_active.return_value = True
                        
                        # Execute the method
                        background_tasks = BackgroundTasks()
                        transaction, subscription = await credit_service.verify_and_process_subscription(
                            user_id=test_user.id,
                            transaction_id="sub_new123",
                            background_tasks=background_tasks
                        )
                        
                        # Verify the result
                        assert transaction is not None
                        assert subscription is not None
                        assert subscription.stripe_subscription_id == "sub_new123"
                        assert subscription.id != test_subscription.id  # Should be a new subscription
                        
                        # Verify the old subscription was cancelled
                        old_subscription = await credit_service.get_subscription_by_id(test_subscription.id)
                        assert old_subscription.is_active is False
                        
                        # Verify the mocks were called correctly
                        mock_verify.assert_called_once_with("sub_new123")
                        mock_check.assert_called_once_with(test_user.id)
                        mock_cancel.assert_called_once_with(test_subscription.stripe_subscription_id)
                        mock_find.assert_called_once_with("price_test123")
                        mock_active.assert_called_once_with("sub_new123")

@pytest.mark.asyncio
async def test_cancel_subscription(credit_service: CreditService, test_subscription: Subscription):
    """Test cancelling a subscription."""
    # Mock the cancel_subscription method to return True
    with patch.object(credit_service.stripe_service, 'cancel_subscription', new_callable=AsyncMock) as mock_cancel:
        mock_cancel.return_value = True
        
        # Execute the method
        result = await credit_service.cancel_subscription(
            subscription_id=test_subscription.id,
            cancel_in_stripe=True
        )
        
        # Verify the result
        assert result is True
        
        # Verify the subscription was updated
        subscription = await credit_service.get_subscription_by_id(test_subscription.id)
        assert subscription.is_active is False
        assert subscription.status == "canceled"
        assert subscription.auto_renew is False
        
        # Verify the mock was called correctly
        mock_cancel.assert_called_once_with(test_subscription.stripe_subscription_id)

@pytest.mark.asyncio
async def test_calculate_credits_for_payment_special_case(credit_service: CreditService):
    """Test that a payment of 39.0 results in exactly 100 credits."""
    # Get the transaction service from the credit service
    transaction_service = credit_service.transaction_service
    
    # Test the special case for payment amount of 39.0
    payment_amount = Decimal("39.0")
    credit_amount = await transaction_service._calculate_credits_for_payment(payment_amount)
    
    # Verify that the credit amount is exactly 100
    assert credit_amount == Decimal("100.0")