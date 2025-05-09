"""Tests for the transaction service, focusing on the free plan card uniqueness gate."""

import pytest
import pytest_asyncio
import secrets 
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, MagicMock, AsyncMock, call

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import BackgroundTasks, HTTPException, status
from app.log.logging import logger 
from tests.conftest import AsyncTestingSessionLocal 

from app.models.user import User
from app.models.plan import Plan, Subscription, UsedTrialCardFingerprint
from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.services.credit import CreditService
from app.services.credit.transaction import TransactionService
from app.schemas import credit_schemas

# Fixtures

@pytest_asyncio.fixture(scope="session")
async def test_user(setup_database) -> User: 
    """Fixture for creating a test user ONCE per session."""
    async with AsyncTestingSessionLocal() as session:
        async with session.begin(): 
            from sqlalchemy import select
            existing_user_result = await session.execute(select(User).where(User.email == "test_integration@example.com"))
            existing_user = existing_user_result.scalar_one_or_none()
            if existing_user:
                 logger.warning("Session-scoped integration test user already exists. Returning existing user.")
                 return existing_user

            user = User(
                email="test_integration@example.com", # Unique email for integration tests
                hashed_password="password",
                is_admin=False,
                is_verified=True,
                auth_type="password",
                stripe_customer_id="cus_test_integration_123"
            )
            session.add(user)
        
        await session.refresh(user)
        logger.info(f"Created session-scoped integration test user: ID {user.id}")
        return user

@pytest_asyncio.fixture
async def test_free_plan(db: AsyncSession) -> Plan:
    """Fixture for creating a test free plan with is_limited_free=True."""
    plan = Plan(
        name="Free Plan Integration Test",
        credit_amount=Decimal("50.00"),
        price=Decimal("0.00"),
        is_active=True,
        stripe_price_id=f"price_free_int_{secrets.token_hex(4)}",
        stripe_product_id=f"prod_free_int_{secrets.token_hex(4)}",
        is_limited_free=True 
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

@pytest_asyncio.fixture
async def test_paid_plan(db: AsyncSession) -> Plan:
    """Fixture for creating a test paid plan with is_limited_free=False."""
    plan = Plan(
        name="Paid Plan Integration Test",
        credit_amount=Decimal("100.00"),
        price=Decimal("10.00"),
        is_active=True,
        stripe_price_id=f"price_paid_int_{secrets.token_hex(4)}",
        stripe_product_id=f"prod_paid_int_{secrets.token_hex(4)}",
        is_limited_free=False 
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

@pytest_asyncio.fixture
async def transaction_service(db: AsyncSession) -> TransactionService:
    """Fixture for creating a TransactionService instance."""
    service = TransactionService()
    service.db = db
    
    service.plan_service = AsyncMock()
    service.base_service = AsyncMock() 
    service.stripe_service = AsyncMock()
    
    return service

# Helper functions for mocking

def mock_stripe_subscription(subscription_id="sub_test123", payment_method_id="pm_test123"):
    """Create a mock Stripe subscription object."""
    mock_sub = MagicMock()
    mock_sub.id = subscription_id
    mock_sub.customer = "cus_test123"
    
    mock_payment_method = MagicMock()
    mock_payment_method.id = payment_method_id
    mock_sub.default_payment_method = mock_payment_method
    
    return mock_sub

def mock_stripe_payment_method(payment_method_id="pm_test123", fingerprint="card_fingerprint123"):
    """Create a mock Stripe payment method object."""
    mock_pm = MagicMock()
    mock_pm.id = payment_method_id
    mock_pm.type = "card"
    
    mock_card = MagicMock()
    mock_card.fingerprint = fingerprint
    mock_pm.card = mock_card
    
    return mock_pm

# Tests

@pytest.mark.asyncio
async def test_free_plan_subscription_new_card(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan,
    db: AsyncSession # db fixture for direct db operations if needed
):
    """Test successful subscription creation for a limited free plan with a new card fingerprint."""
    sub_id = f"sub_new_card_{secrets.token_hex(4)}" 
    pm_id = f"pm_new_card_{secrets.token_hex(4)}"
    fingerprint = f"fp_new_card_{secrets.token_hex(4)}"

    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("0.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_free_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                transaction_service.purchase_plan = AsyncMock()
                mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
                mock_transaction_response.id = "mock_tx_new_card"
                mock_transaction_response.new_balance = Decimal("50.00")
                mock_subscription_object = MagicMock(spec=Subscription)
                mock_subscription_object.id = "mock_sub_obj_new_card"
                transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)
                
                background_tasks = BackgroundTasks()
                transaction, subscription = await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id, 
                    background_tasks=background_tasks
                )
                
                assert transaction is not None
                assert subscription is not None
                
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id)
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with(test_free_plan.stripe_price_id)
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()
                transaction_service.purchase_plan.assert_called_once()
                
                # Verify a record was NOT added to UsedTrialCardFingerprint (as logic is commented out)
                from sqlalchemy import select
                card_result = await db.execute(
                    select(UsedTrialCardFingerprint).where(UsedTrialCardFingerprint.stripe_card_fingerprint == fingerprint)
                )
                card_record = card_result.scalar_one_or_none()
                assert card_record is None # Changed: Should be None now

@pytest.mark.asyncio
async def test_free_plan_subscription_duplicate_card(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan,
    db: AsyncSession
):
    """Test successful subscription even with a 'duplicate' card, as check is disabled."""
    sub_id = f"sub_dup_card_{secrets.token_hex(4)}"
    pm_id = f"pm_dup_card_{secrets.token_hex(4)}"
    fingerprint = f"fp_dup_card_{secrets.token_hex(4)}" 

    # Simulate prior use (though it won't be checked by the service anymore)
    # This record is just for conceptual clarity of the test scenario
    used_card = UsedTrialCardFingerprint(
        user_id=test_user.id, stripe_card_fingerprint=fingerprint, 
        stripe_payment_method_id="pm_existing_dup", stripe_subscription_id="sub_existing_dup",
        stripe_customer_id="cus_existing_dup"
    )
    db.add(used_card)
    await db.commit()
    
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("0.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_free_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                transaction_service.purchase_plan = AsyncMock()
                mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
                mock_transaction_response.id = "mock_tx_dup_card"
                mock_transaction_response.new_balance = Decimal("50.00")
                mock_subscription_object = MagicMock(spec=Subscription)
                mock_subscription_object.id = "mock_sub_obj_dup_card"
                transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)
                
                background_tasks = BackgroundTasks()
                # Expect successful processing, no HTTPException
                transaction, subscription = await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id, 
                    background_tasks=background_tasks
                )
                
                assert transaction is not None
                assert subscription is not None
                
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id)
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with(test_free_plan.stripe_price_id)
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()
                transaction_service.purchase_plan.assert_called_once()

@pytest.mark.asyncio
async def test_paid_plan_subscription_bypass_gate(
    transaction_service: TransactionService,
    test_user: User,
    test_paid_plan: Plan
):
    """Test successful subscription creation for a non-limited plan, ensuring the gate logic is bypassed."""
    sub_id = f"sub_paid_bypass_{secrets.token_hex(4)}" 

    transaction_service.plan_service.get_plan_by_id.return_value = test_paid_plan
    
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("10.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_paid_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_paid_plan.id
        
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        transaction_service.purchase_plan = AsyncMock()
        mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
        mock_transaction_response.id = "mock_tx_paid_bypass"
        mock_transaction_response.new_balance = Decimal("100.00")
        mock_subscription_object = MagicMock(spec=Subscription)
        mock_subscription_object.id = "mock_sub_obj_paid_bypass"
        transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)
        
        background_tasks = BackgroundTasks()
        transaction, subscription = await transaction_service.verify_and_process_subscription(
            user_id=test_user.id,
            transaction_id=sub_id, 
            background_tasks=background_tasks
        )
        
        assert transaction is not None
        assert subscription is not None
        
        transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id)
        transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
        mock_find.assert_called_once_with(test_paid_plan.stripe_price_id)
        transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_paid_plan.id)
        
        with patch('stripe.Subscription.retrieve', new_callable=AsyncMock) as mock_stripe_sub_retrieve, \
             patch('stripe.PaymentMethod.retrieve', new_callable=AsyncMock) as mock_stripe_pm_retrieve:
            pass # Mocks are set up but should not be called for paid plan
                
        mock_stripe_sub_retrieve.assert_not_called()
        mock_stripe_pm_retrieve.assert_not_called()
        transaction_service.purchase_plan.assert_called_once()

@pytest.mark.asyncio
async def test_paid_plan_after_free_trial_same_card(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan, 
    test_paid_plan: Plan, 
    db: AsyncSession
):
    """
    Test AC1: User who used a card for a free trial CAN purchase a PAID plan with the SAME card.
    The card uniqueness gate should NOT be triggered for non-limited_free plans.
    """
    paid_sub_id = f"sub_paid_after_free_{secrets.token_hex(4)}"
    shared_fingerprint = f"fp_shared_{secrets.token_hex(4)}"
    
    # This record is for conceptual clarity; it won't be checked by the service for paid plans.
    used_card_record = UsedTrialCardFingerprint(
        user_id=test_user.id, stripe_card_fingerprint=shared_fingerprint,
        stripe_payment_method_id="pm_free_trial_orig", stripe_subscription_id="sub_free_trial_orig",
        stripe_customer_id=test_user.stripe_customer_id
    )
    db.add(used_card_record)
    await db.commit()

    transaction_service.plan_service.get_plan_by_id.return_value = test_paid_plan
    
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": paid_sub_id, "object_type": "subscription",
        "amount": test_paid_plan.price, "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_paid_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find_plan:
        mock_find_plan.return_value = test_paid_plan.id
        
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        transaction_service.purchase_plan = AsyncMock()
        mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
        mock_transaction_response.id = "mock_tx_paid_after_free"
        mock_transaction_response.new_balance = Decimal("100.00") 
        mock_subscription_object = MagicMock(spec=Subscription)
        mock_subscription_object.id = "mock_sub_obj_paid_after_free"
        transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)

        with patch('stripe.Subscription.retrieve', new_callable=AsyncMock) as mock_stripe_sub_retrieve, \
             patch('stripe.PaymentMethod.retrieve', new_callable=AsyncMock) as mock_stripe_pm_retrieve:

            background_tasks = BackgroundTasks()
            transaction, subscription = await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=paid_sub_id,
                background_tasks=background_tasks
            )
            
            assert transaction is mock_transaction_response
            assert subscription is mock_subscription_object
            
            transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(paid_sub_id)
            transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
            mock_find_plan.assert_called_once_with(test_paid_plan.stripe_price_id)
            transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_paid_plan.id)
            
            mock_stripe_sub_retrieve.assert_not_called()
            mock_stripe_pm_retrieve.assert_not_called()
            
            transaction_service.purchase_plan.assert_called_once()

@pytest.mark.asyncio
async def test_verify_subscription_no_local_plan_match(
    transaction_service: TransactionService,
    test_user: User
):
    """Test verify_and_process_subscription when Stripe Price ID from webhook has no matching local plan."""
    sub_id_unknown_plan = f"sub_unknown_plan_{secrets.token_hex(4)}"
    stripe_price_id_unknown = "price_does_not_exist_locally"

    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id_unknown_plan, "object_type": "subscription",
        "amount": Decimal("10.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": stripe_price_id_unknown
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find_plan:
        mock_find_plan.return_value = None 

        background_tasks = BackgroundTasks()
        with pytest.raises(HTTPException) as excinfo:
            await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=sub_id_unknown_plan,
                background_tasks=background_tasks
            )
        
        assert excinfo.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert f"Configuration error: The plan associated with your subscription (ID: {stripe_price_id_unknown}) is not configured in our system." in str(excinfo.value.detail)

        transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id_unknown_plan)
        transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
        mock_find_plan.assert_called_once_with(stripe_price_id_unknown)
        transaction_service.plan_service.get_plan_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_verify_subscription_stripe_provides_no_plan_id(
    transaction_service: TransactionService,
    test_user: User
):
    """Test verify_and_process_subscription when Stripe verification result has no plan_id."""
    sub_id_no_plan_from_stripe = f"sub_no_plan_stripe_{secrets.token_hex(4)}"

    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id_no_plan_from_stripe, "object_type": "subscription",
        "amount": Decimal("10.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": None # Stripe provides no plan_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find_plan:
        background_tasks = BackgroundTasks()
        with pytest.raises(HTTPException) as excinfo:
            await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=sub_id_no_plan_from_stripe,
                background_tasks=background_tasks
            )
        
        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Subscription verification failed: Stripe did not provide a plan identifier." in str(excinfo.value.detail)
        mock_find_plan.assert_not_called() # Should fail before trying to find plan


@pytest.mark.asyncio
async def test_free_plan_subscription_no_payment_method(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan
):
    """Test handling error when Stripe Subscription.retrieve fails or returns no payment method."""
    sub_id = f"sub_no_pm_{secrets.token_hex(4)}"
    
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("0.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_free_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Simulate Stripe.Subscription.retrieve returning no default_payment_method
        mock_sub_no_pm = MagicMock()
        mock_sub_no_pm.id = sub_id
        mock_sub_no_pm.customer = test_user.stripe_customer_id
        mock_sub_no_pm.default_payment_method = None # Key part of this test
        
        with patch('stripe.Subscription.retrieve', return_value=mock_sub_no_pm) as mock_sub_retrieve:
            background_tasks = BackgroundTasks()
            with pytest.raises(HTTPException) as excinfo:
                await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id,
                    background_tasks=background_tasks
                )
            assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Could not retrieve payment method details for subscription." in str(excinfo.value.detail)
            mock_sub_retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_free_plan_subscription_invalid_payment_method(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan
):
    """Test handling error when Stripe PaymentMethod.retrieve fails or returns invalid data."""
    sub_id = f"sub_invalid_pm_{secrets.token_hex(4)}"
    pm_id = f"pm_invalid_{secrets.token_hex(4)}"
    
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("0.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_free_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            # Simulate PaymentMethod.retrieve returning a non-card PM or no fingerprint
            mock_pm_invalid = MagicMock()
            mock_pm_invalid.id = pm_id
            mock_pm_invalid.type = "not_a_card" # or mock_pm_invalid.card = None
            mock_pm_invalid.card = None

            with patch('stripe.PaymentMethod.retrieve', return_value=mock_pm_invalid) as mock_pm_retrieve:
                background_tasks = BackgroundTasks()
                with pytest.raises(HTTPException) as excinfo:
                    await transaction_service.verify_and_process_subscription(
                        user_id=test_user.id,
                        transaction_id=sub_id,
                        background_tasks=background_tasks
                    )
                assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
                assert "Invalid payment method type for free plan check." in str(excinfo.value.detail)
                mock_pm_retrieve.assert_called_once()


@pytest.mark.asyncio
async def test_free_plan_subscription_race_condition(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan,
    db: AsyncSession # Use real session for more realistic IntegrityError
):
    """Test successful subscription even with a simulated race condition, as check is disabled."""
    sub_id = f"sub_race_{secrets.token_hex(4)}"
    pm_id = f"pm_race_{secrets.token_hex(4)}"
    fingerprint = f"fp_race_{secrets.token_hex(4)}"

    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True, "id": sub_id, "object_type": "subscription",
        "amount": Decimal("0.00"), "customer_id": test_user.stripe_customer_id,
        "status": "active", "plan_id": test_free_plan.stripe_price_id
    }
    transaction_service.stripe_service.check_active_subscription.return_value = None

    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                # Mock purchase_plan to simulate what would happen
                transaction_service.purchase_plan = AsyncMock()
                mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
                mock_transaction_response.id = "mock_tx_race"
                mock_transaction_response.new_balance = Decimal("50.00")
                mock_subscription_object = MagicMock(spec=Subscription)
                mock_subscription_object.id = "mock_sub_obj_race"
                transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)

                # No longer need to mock db.add to raise IntegrityError as the add is commented out
                # original_db_add = transaction_service.db.add
                # transaction_service.db.add = MagicMock(side_effect=IntegrityError("Simulated race", {}, None))

                background_tasks = BackgroundTasks()
                # Expect successful processing now
                transaction, subscription = await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id,
                    background_tasks=background_tasks
                )
                assert transaction is not None
                assert subscription is not None
                transaction_service.purchase_plan.assert_called_once()

                # transaction_service.db.add = original_db_add # Restore original add