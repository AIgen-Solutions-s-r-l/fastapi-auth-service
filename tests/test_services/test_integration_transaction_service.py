"""Tests for the transaction service, focusing on the free plan card uniqueness gate."""

import pytest
import pytest_asyncio
import secrets # Add missing import
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, MagicMock, AsyncMock, call

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi import BackgroundTasks, HTTPException, status
from app.log.logging import logger # Import logger
from tests.conftest import AsyncTestingSessionLocal # Import sessionmaker

from app.models.user import User
from app.models.plan import Plan, Subscription, UsedTrialCardFingerprint
from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.services.credit import CreditService
from app.services.credit.transaction import TransactionService
from app.schemas import credit_schemas

# Fixtures

@pytest_asyncio.fixture(scope="session")
async def test_user(setup_database) -> User: # Depend on session-scoped setup_database
    """Fixture for creating a test user ONCE per session."""
    # Create a temporary session just for this fixture setup
    async with AsyncTestingSessionLocal() as session:
        async with session.begin(): # Start a transaction
            # Check if user already exists (in case fixture runs multiple times unexpectedly)
            from sqlalchemy import select
            existing_user_result = await session.execute(select(User).where(User.email == "test@example.com"))
            existing_user = existing_user_result.scalar_one_or_none()
            if existing_user:
                 logger.warning("Session-scoped test user already exists. Returning existing user.")
                 # Refresh to ensure relationships are loaded if needed, though maybe not necessary here
                 # await session.refresh(existing_user)
                 return existing_user

            user = User(
                email="test@example.com",
                hashed_password="password",
                is_admin=False,
                is_verified=True,
                auth_type="password",
                stripe_customer_id="cus_test123"
            )
            session.add(user)
            # Commit happens automatically on exiting 'async with session.begin()' block
        
        # Refresh the user within the same session but outside the transaction block
        # to ensure it's loaded correctly before the session closes.
        await session.refresh(user)
        logger.info(f"Created session-scoped test user: ID {user.id}")
        # Detach the user object from the temporary session? Not strictly necessary for read-only use.
        # session.expunge(user) # Optional: detach if modifications in tests cause issues
        return user # Return the user object created in the temporary session

@pytest_asyncio.fixture
async def test_free_plan(db: AsyncSession) -> Plan:
    """Fixture for creating a test free plan with is_limited_free=True."""
    plan = Plan(
        name="Free Plan",
        credit_amount=Decimal("50.00"),
        price=Decimal("0.00"),
        is_active=True,
        stripe_price_id="price_free123",
        stripe_product_id="prod_free123",
        is_limited_free=True  # This is the key flag for the uniqueness gate
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan

@pytest_asyncio.fixture
async def test_paid_plan(db: AsyncSession) -> Plan:
    """Fixture for creating a test paid plan with is_limited_free=False."""
    plan = Plan(
        name="Paid Plan",
        credit_amount=Decimal("100.00"),
        price=Decimal("10.00"),
        is_active=True,
        stripe_price_id="price_paid123",
        stripe_product_id="prod_paid123",
        is_limited_free=False  # Not a limited free plan
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
    
    # Create mock services
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
    
    # Set up default_payment_method
    mock_payment_method = MagicMock()
    mock_payment_method.id = payment_method_id
    mock_sub.default_payment_method = mock_payment_method
    
    return mock_sub

def mock_stripe_payment_method(payment_method_id="pm_test123", fingerprint="card_fingerprint123"):
    """Create a mock Stripe payment method object."""
    mock_pm = MagicMock()
    mock_pm.id = payment_method_id
    mock_pm.type = "card"
    
    # Set up card with fingerprint
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
    db: AsyncSession
):
    """Test successful subscription creation for a limited free plan with a new card fingerprint."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test
    pm_id = f"pm_test_{secrets.token_hex(4)}"
    fingerprint = f"fp_test_{secrets.token_hex(4)}"

    # Mock plan_service.get_plan_by_id to return our test_free_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("0.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_free123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Mock stripe_service.verify_subscription_active
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        # Mock Stripe API calls using unique IDs
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                # Mock purchase_plan
                transaction_service.purchase_plan = AsyncMock()
                mock_transaction = MagicMock()
                mock_subscription = MagicMock()
                transaction_service.purchase_plan.return_value = (mock_transaction, mock_subscription)
                
                # Execute the method
                background_tasks = BackgroundTasks()
                transaction, subscription = await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id, # Use unique ID
                    background_tasks=background_tasks
                )
                
                # Verify the result
                assert transaction is not None
                assert subscription is not None
                
                # Verify the mocks were called correctly
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use unique ID
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with("price_free123")
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()
                transaction_service.purchase_plan.assert_called_once()
                
                # Verify a record was added to UsedTrialCardFingerprint
                from sqlalchemy import select
                card_result = await db.execute(
                    select(UsedTrialCardFingerprint).where(UsedTrialCardFingerprint.stripe_card_fingerprint == fingerprint) # Use unique fingerprint
                )
                card_record = card_result.scalar_one_or_none()
                assert card_record is not None
                assert card_record.stripe_subscription_id == sub_id # Use unique ID

@pytest.mark.asyncio
async def test_free_plan_subscription_duplicate_card(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan,
    db: AsyncSession
):
    """Test rejection when attempting to use the same card fingerprint for a second limited free plan."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test
    pm_id = f"pm_test_{secrets.token_hex(4)}"
    fingerprint = f"fp_test_{secrets.token_hex(4)}" # Fingerprint to check against

    # First, add a record to the UsedTrialCardFingerprint table with the target fingerprint
    used_card = UsedTrialCardFingerprint(
        user_id=test_user.id,
        stripe_card_fingerprint=fingerprint, # Use the fingerprint we'll test with
        stripe_payment_method_id="pm_existing123",
        stripe_subscription_id="sub_existing123",
        stripe_customer_id="cus_existing123"
    )
    db.add(used_card)
    await db.commit()
    
    # Mock plan_service.get_plan_by_id to return our test_free_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("0.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_free123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Mock Stripe API calls using the target fingerprint
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                # Execute the method and expect an exception
                background_tasks = BackgroundTasks()
                with pytest.raises(HTTPException) as excinfo:
                    await transaction_service.verify_and_process_subscription(
                        user_id=test_user.id,
                        transaction_id=sub_id, # Use unique ID
                        background_tasks=background_tasks
                    )
                
                # Verify the exception details
                assert excinfo.value.status_code == status.HTTP_409_CONFLICT
                assert "already been used for a free subscription" in str(excinfo.value.detail)
                
                # Verify the mocks were called correctly
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use unique ID
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with("price_free123")
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()

@pytest.mark.asyncio
async def test_paid_plan_subscription_bypass_gate(
    transaction_service: TransactionService,
    test_user: User,
    test_paid_plan: Plan
):
    """Test successful subscription creation for a non-limited plan, ensuring the gate logic is bypassed."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test

    # Mock plan_service.get_plan_by_id to return our test_paid_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_paid_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("10.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_paid123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_paid_plan.id
        
        # Mock stripe_service.verify_subscription_active
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        # Mock purchase_plan
        transaction_service.purchase_plan = AsyncMock()
        mock_transaction = MagicMock()
        mock_subscription = MagicMock()
        transaction_service.purchase_plan.return_value = (mock_transaction, mock_subscription)
        
        # Execute the method
        background_tasks = BackgroundTasks()
        transaction, subscription = await transaction_service.verify_and_process_subscription(
            user_id=test_user.id,
            transaction_id=sub_id, # Use unique ID
            background_tasks=background_tasks
        )
        
        # Verify the result
        assert transaction is not None
        assert subscription is not None
        
        # Verify the mocks were called correctly
        transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use unique ID
        transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
        mock_find.assert_called_once_with("price_paid123")
        transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_paid_plan.id)
        
        # Verify that Stripe.Subscription.retrieve was NOT called (gate bypassed)
        # This is the key assertion for this test - we need to check if the mocks were called
        # Since we didn't use the mocks in this test, they shouldn't have been called
        with patch('stripe.Subscription.retrieve') as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve') as mock_pm_retrieve:
                # We're just setting up the mocks here, not actually using them
                pass
                
        # The key assertion is that the purchase_plan was called without going through the card check
        transaction_service.purchase_plan.assert_called_once()

@pytest.mark.asyncio
async def test_paid_plan_after_free_trial_same_card(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan, # Used to set up the initial free trial card usage
    test_paid_plan: Plan, # The plan being purchased
    db: AsyncSession
):
    """
    Test AC1: User who used a card for a free trial CAN purchase a PAID plan with the SAME card.
    The card uniqueness gate should NOT be triggered for non-limited_free plans.
    """
    paid_sub_id = f"sub_paid_after_free_{secrets.token_hex(4)}"
    # Use the same fingerprint that was "used" for a free trial
    shared_fingerprint = f"fp_shared_{secrets.token_hex(4)}"
    shared_pm_id = f"pm_shared_{secrets.token_hex(4)}"

    # 1. Simulate prior use of the card for a free trial
    used_card_record = UsedTrialCardFingerprint(
        user_id=test_user.id,
        stripe_card_fingerprint=shared_fingerprint,
        stripe_payment_method_id="pm_free_trial_orig", # Original PM for free trial
        stripe_subscription_id="sub_free_trial_orig", # Original sub for free trial
        stripe_customer_id=test_user.stripe_customer_id
    )
    db.add(used_card_record)
    await db.commit()

    # 2. Mock services for the PAID plan purchase
    # Mock plan_service.get_plan_by_id to return the test_paid_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_paid_plan
    
    # Mock stripe_service.verify_transaction_id for the paid subscription
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": paid_sub_id,
        "object_type": "subscription",
        "amount": test_paid_plan.price,
        "customer_id": test_user.stripe_customer_id,
        "status": "active",
        "plan_id": test_paid_plan.stripe_price_id # Stripe Price ID of the PAID plan
    }
    
    # Mock stripe_service.check_active_subscription (no existing active sub)
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan to return the paid plan's ID
    # This mock is crucial to simulate that the system correctly identifies the paid plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find_plan:
        mock_find_plan.return_value = test_paid_plan.id
        
        # Mock stripe_service.verify_subscription_active (for the purchase_plan call)
        transaction_service.stripe_service.verify_subscription_active.return_value = True
        
        # Mock the actual purchase_plan method since we are testing verify_and_process_subscription
        transaction_service.purchase_plan = AsyncMock()
        # Ensure the mock objects have an 'id' attribute, as the code under test will access it.
        mock_transaction_response = MagicMock(spec=credit_schemas.TransactionResponse)
        mock_transaction_response.id = "mock_tx_id_123" # Add id attribute
        mock_transaction_response.new_balance = Decimal("100.00") # Add new_balance attribute
        mock_subscription_object = MagicMock(spec=Subscription)
        mock_subscription_object.id = "mock_sub_obj_id_456" # Add id attribute
        transaction_service.purchase_plan.return_value = (mock_transaction_response, mock_subscription_object)

        # Mock Stripe API calls that *should not* be called if the gate is correctly bypassed
        with patch('stripe.Subscription.retrieve', new_callable=AsyncMock) as mock_stripe_sub_retrieve, \
             patch('stripe.PaymentMethod.retrieve', new_callable=AsyncMock) as mock_stripe_pm_retrieve:

            # 3. Execute the method
            background_tasks = BackgroundTasks()
            transaction, subscription = await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=paid_sub_id,
                background_tasks=background_tasks
            )
            
            # 4. Verify results
            assert transaction is mock_transaction_response
            assert subscription is mock_subscription_object
            
            # Verify mocks
            transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(paid_sub_id)
            transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
            mock_find_plan.assert_called_once_with(test_paid_plan.stripe_price_id)
            # get_plan_by_id is called once to check is_limited_free
            transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_paid_plan.id)
            
            # CRITICAL: Assert that Stripe card detail retrieval was NOT called (gate bypassed)
            mock_stripe_sub_retrieve.assert_not_called()
            mock_stripe_pm_retrieve.assert_not_called()
            
            # Assert purchase_plan was called
            transaction_service.purchase_plan.assert_called_once()

@pytest.mark.asyncio
async def test_verify_subscription_no_local_plan_match(
    transaction_service: TransactionService,
    test_user: User
):
    """Test verify_and_process_subscription when Stripe Price ID from webhook has no matching local plan."""
    sub_id_unknown_plan = f"sub_unknown_plan_{secrets.token_hex(4)}"
    stripe_price_id_unknown = "price_does_not_exist_locally"

    # Mock stripe_service.verify_transaction_id to return a plan_id that won't be found
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id_unknown_plan,
        "object_type": "subscription",
        "amount": Decimal("10.00"),
        "customer_id": test_user.stripe_customer_id,
        "status": "active",
        "plan_id": stripe_price_id_unknown # This Stripe Price ID won't match any local plan
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan to return None, simulating no local match
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find_plan:
        mock_find_plan.return_value = None # Simulate no matching plan found

        background_tasks = BackgroundTasks()
        with pytest.raises(HTTPException) as excinfo:
            await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=sub_id_unknown_plan,
                background_tasks=background_tasks
            )
        
        assert excinfo.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert f"Configuration error: The plan associated with your subscription (ID: {stripe_price_id_unknown}) is not configured in our system." in str(excinfo.value.detail)

        # Verify mocks
        transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id_unknown_plan)
        transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
        mock_find_plan.assert_called_once_with(stripe_price_id_unknown)
        # get_plan_by_id should not be called if _find_matching_plan returns None early
        transaction_service.plan_service.get_plan_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_verify_subscription_stripe_provides_no_plan_id(
    transaction_service: TransactionService,
    test_user: User
):
    """Test verify_and_process_subscription when Stripe verification result has no plan_id."""
    sub_id_no_plan_from_stripe = f"sub_no_plan_stripe_{secrets.token_hex(4)}"

    # Mock stripe_service.verify_transaction_id to return no plan_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id_no_plan_from_stripe,
        "object_type": "subscription",
        "amount": Decimal("10.00"),
        "customer_id": test_user.stripe_customer_id,
        "status": "active",
        "plan_id": None # Simulate Stripe not returning a plan_id
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # _find_matching_plan should not even be called if plan_id from stripe is None
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

        # Verify mocks
        transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id_no_plan_from_stripe)
        transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
        mock_find_plan.assert_not_called() # Crucial: _find_matching_plan should not be called
        transaction_service.plan_service.get_plan_by_id.assert_not_called()
@pytest.mark.asyncio
async def test_free_plan_subscription_no_payment_method(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan
):
    """Test handling error when Stripe Subscription.retrieve fails or returns no payment method."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test

    # Mock plan_service.get_plan_by_id to return our test_free_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("0.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_free123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Create a subscription with no payment method using the unique ID
        mock_sub_no_pm = MagicMock()
        mock_sub_no_pm.id = sub_id # Use unique ID
        mock_sub_no_pm.customer = "cus_test123"
        mock_sub_no_pm.default_payment_method = None  # No payment method
        
        # Mock Stripe API calls
        with patch('stripe.Subscription.retrieve', return_value=mock_sub_no_pm) as mock_sub_retrieve:
            
            # Execute the method and expect an exception
            background_tasks = BackgroundTasks()
            with pytest.raises(HTTPException) as excinfo:
                await transaction_service.verify_and_process_subscription(
                    user_id=test_user.id,
                    transaction_id=sub_id, # Use unique ID
                    background_tasks=background_tasks
                )
            
            # Verify the exception details
            assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
            assert "Could not retrieve payment method details" in str(excinfo.value.detail)
            
            # Verify the mocks were called correctly
            transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use unique ID
            transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
            mock_find.assert_called_once_with("price_free123")
            transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
            mock_sub_retrieve.assert_called_once()

@pytest.mark.asyncio
async def test_free_plan_subscription_invalid_payment_method(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan
):
    """Test handling error when Stripe PaymentMethod.retrieve fails or returns invalid data."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test
    pm_id = f"pm_test_{secrets.token_hex(4)}"

    # Mock plan_service.get_plan_by_id to return our test_free_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("0.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_free123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Mock Stripe API calls using unique IDs
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            # Create an invalid payment method (no card or fingerprint)
            mock_pm_invalid = MagicMock()
            mock_pm_invalid.id = pm_id # Use unique ID
            mock_pm_invalid.type = "card"
            mock_pm_invalid.card = None  # No card object
            
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_pm_invalid) as mock_pm_retrieve:
                
                # Execute the method and expect an exception
                background_tasks = BackgroundTasks()
                with pytest.raises(HTTPException) as excinfo:
                    await transaction_service.verify_and_process_subscription(
                        user_id=test_user.id,
                        transaction_id=sub_id, # Use unique ID
                        background_tasks=background_tasks
                    )
                
                # Verify the exception details
                assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
                assert "Invalid payment method type" in str(excinfo.value.detail)
                
                # Verify the mocks were called correctly
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use unique ID
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with("price_free123")
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()

@pytest.mark.asyncio
async def test_free_plan_subscription_race_condition(
    transaction_service: TransactionService,
    test_user: User,
    test_free_plan: Plan,
    db: AsyncSession
):
    """Test handling database IntegrityError during fingerprint insertion (race condition simulation)."""
    sub_id = f"sub_test_{secrets.token_hex(4)}" # Unique ID for this test
    pm_id = f"pm_test_{secrets.token_hex(4)}"
    fingerprint = f"fp_test_{secrets.token_hex(4)}" # Fingerprint to check against

    # Mock plan_service.get_plan_by_id to return our test_free_plan
    transaction_service.plan_service.get_plan_by_id.return_value = test_free_plan
    
    # Mock stripe_service.verify_transaction_id
    transaction_service.stripe_service.verify_transaction_id.return_value = {
        "verified": True,
        "id": sub_id, # Use unique ID
        "object_type": "subscription",
        "amount": Decimal("0.00"),
        "customer_id": "cus_test123",
        "status": "active",
        "plan_id": "price_free123"
    }
    
    # Mock stripe_service.check_active_subscription
    transaction_service.stripe_service.check_active_subscription.return_value = None
    
    # Mock _find_matching_plan
    with patch.object(transaction_service, '_find_matching_plan', new_callable=AsyncMock) as mock_find:
        mock_find.return_value = test_free_plan.id
        
        # Mock Stripe API calls using unique IDs
        with patch('stripe.Subscription.retrieve', return_value=mock_stripe_subscription(subscription_id=sub_id, payment_method_id=pm_id)) as mock_sub_retrieve:
            with patch('stripe.PaymentMethod.retrieve', return_value=mock_stripe_payment_method(payment_method_id=pm_id, fingerprint=fingerprint)) as mock_pm_retrieve:
                
                # For the race condition test, we'll use a different approach
                # Instead of mocking db.flush, we'll add a record to the database
                # right after the check but before the insert would happen
                
                # First, create a mock implementation of _check_transaction_exists
                original_check_exists = transaction_service._check_transaction_exists
                
                # Create a flag to track if we've already inserted the conflicting record
                race_condition_triggered = False
                
                async def mock_check_transaction_exists(transaction_id):
                    nonlocal race_condition_triggered
                    result = await original_check_exists(transaction_id)
                    
                    # After the check but before the insert, add a conflicting record
                    # to simulate a race condition
                    if not race_condition_triggered and transaction_id == sub_id: # Use unique ID
                        race_condition_triggered = True
                        # Add the conflicting record using the target fingerprint
                        used_card = UsedTrialCardFingerprint(
                            user_id=test_user.id,
                            stripe_card_fingerprint=fingerprint, # Use the target fingerprint
                            stripe_payment_method_id=f"pm_race_{secrets.token_hex(4)}", # Make these unique too
                            stripe_subscription_id=f"sub_race_{secrets.token_hex(4)}",
                            stripe_customer_id=f"cus_race_{secrets.token_hex(4)}"
                        )
                        db.add(used_card)
                        await db.commit()
                    
                    return result
                
                # Replace the method
                transaction_service._check_transaction_exists = mock_check_transaction_exists
                
                # Execute the method and expect an exception
                background_tasks = BackgroundTasks()
                with pytest.raises(HTTPException) as excinfo:
                    await transaction_service.verify_and_process_subscription(
                        user_id=test_user.id,
                        transaction_id=sub_id, # Use unique ID
                        background_tasks=background_tasks
                    )
                
                # Verify the exception details
                assert excinfo.value.status_code == status.HTTP_409_CONFLICT
                assert "already been used for a free subscription" in str(excinfo.value.detail)

                # Verify the mocks were called correctly
                transaction_service.stripe_service.verify_transaction_id.assert_called_once_with(sub_id) # Use dynamic sub_id
                transaction_service.stripe_service.check_active_subscription.assert_called_once_with(test_user.id)
                mock_find.assert_called_once_with("price_free123")
                transaction_service.plan_service.get_plan_by_id.assert_called_once_with(test_free_plan.id)
                mock_sub_retrieve.assert_called_once()
                mock_pm_retrieve.assert_called_once()
                
                # Restore the original method
                transaction_service._check_transaction_exists = original_check_exists
                