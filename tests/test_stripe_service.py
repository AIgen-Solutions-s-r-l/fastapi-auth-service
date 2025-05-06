import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import asyncio # Ensure asyncio is imported

from app.services.stripe_service import StripeService
from app.core.config import settings
import stripe  # Import stripe to potentially mock its exceptions
from app.models.user import User as UserModel
from app.models.plan import Subscription as SubscriptionModel
from app.core.exceptions import NotFoundError, DatabaseError as CoreDatabaseError # Renamed to avoid clash
from fastapi import HTTPException

def create_stripe_mock(**kwargs):
    """
    Helper function to create a mock that supports both attribute and dictionary-style access.
    This matches how the StripeService accesses Stripe objects.
    """
    mock = MagicMock()
    
    # Set attributes directly
    for key, value in kwargs.items():
        setattr(mock, key, value)
    
    # Configure dictionary-style access
    def getitem(key):
        return kwargs.get(key, MagicMock())
    
    mock.__getitem__.side_effect = getitem
    
    # Configure .get() method to work like dict.get()
    def get_method(key, default=None):
        return kwargs.get(key, default)
    
    mock.get.side_effect = get_method
    
    return mock

@pytest.fixture
def stripe_service():
    """Fixture to create a StripeService instance in test mode."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
# Initialize with test_mode=True to skip API key validation if needed
        service = StripeService(test_mode=True)
        return service
@pytest.fixture
def mock_db_session():
    """Fixture for a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.scalars = AsyncMock()
    # Mock the return value of scalars().first()
    session.scalars.return_value.first = AsyncMock()
    return session

@pytest.fixture
def stripe_service_with_db(mock_db_session):
    """Fixture to create a StripeService instance with a mocked DB session."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
        service = StripeService(db_session=mock_db_session)
        return service

def create_mock_stripe_subscription(
    id="sub_test123",
    status="active",
    cancel_at_period_end=False,
    current_period_end=int((datetime.now(timezone.utc).timestamp()) + 30 * 24 * 60 * 60), # 30 days from now
    customer="cus_test123",
    **kwargs
):
    """Helper to create a mock Stripe Subscription object."""
    mock_sub = MagicMock(spec=stripe.Subscription)
    mock_sub.id = id
    mock_sub.status = status
    mock_sub.cancel_at_period_end = cancel_at_period_end
    mock_sub.current_period_end = current_period_end
    mock_sub.customer = customer
    
    for key, value in kwargs.items():
        setattr(mock_sub, key, value)
    return mock_sub

@pytest.fixture
def mock_user_active_db_subscription():
    """Fixture for an active user subscription model instance from DB."""
    sub = MagicMock(spec=SubscriptionModel)
    sub.id = "db_sub_1"
    sub.user_id = "user_123"
    sub.stripe_subscription_id = "sub_active_stripe_id"
    sub.status = "active" # or 'trialing'
    sub.plan_id = "plan_1"
    sub.current_period_start = datetime.now(timezone.utc)
    sub.current_period_end = datetime.now(timezone.utc) # Placeholder, Stripe object's value is more relevant
    sub.created_at = datetime.now(timezone.utc)
    sub.updated_at = datetime.now(timezone.utc)
    return sub

# Patch datetime.now for consistent timestamps in tests
@pytest.fixture
def mock_datetime_now(mocker):
    """Fixture to mock datetime.now."""
    mock_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mocker.patch('app.services.stripe_service.datetime', MagicMock(now=MagicMock(return_value=mock_now)))
    return mock_now
        

# --- Tests for find_transaction_by_id ---

@pytest.mark.asyncio
async def test_find_transaction_by_id_payment_intent_success(stripe_service, mocker):
    """Test finding a transaction by ID when it's a PaymentIntent."""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    
    # Create a billing details mock that works with both access patterns
    billing_details_mock = create_stripe_mock(email='test@example.com')
    
    # Create a charge mock that works with both access patterns
    charge_mock = create_stripe_mock(billing_details=billing_details_mock)
    
    # Create a charges mock that works with both access patterns
    charges_mock = create_stripe_mock(data=[charge_mock])
    
    # Create a payment intent mock that works with both access patterns
    mock_payment_intent = create_stripe_mock(
        id='pi_123',
        object='payment_intent',
        amount=5000,
        customer='cus_abc',
        created=timestamp,
        charges=charges_mock
    )

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    # Configure the mock to return the mock_payment_intent when called with stripe.PaymentIntent.retrieve
    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            return mock_payment_intent
        # Simulate failures for other types if needed for strict path testing
        elif func in [stripe.Subscription.retrieve, stripe.Invoice.retrieve, stripe.Charge.retrieve]:
             raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'pi_123'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is not None
    assert result['id'] == transaction_id
    assert result['object_type'] == 'payment_intent'
    assert result['amount'] == Decimal('50.00')
    assert result['customer_id'] == 'cus_abc'
    assert result['customer_email'] == 'test@example.com'
    assert isinstance(result['created_at'], datetime)

    # Assert asyncio.to_thread was called correctly for PaymentIntent
    mock_to_thread.assert_any_call(stripe.PaymentIntent.retrieve, transaction_id)
    # Check it wasn't called for others after success (due to early return)
    assert not any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in mock_to_thread.call_args_list)


@pytest.mark.asyncio
async def test_find_transaction_by_id_subscription_success(stripe_service, mocker):
    """Test finding a transaction by ID when it's a Subscription."""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    
    # Create an items mock that works with both access patterns
    items_data = [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]
    items_mock = create_stripe_mock(data=items_data)
    
    # Create a subscription mock that works with both access patterns
    mock_subscription = create_stripe_mock(
        id='sub_456',
        object='subscription',
        customer='cus_def',
        created=timestamp,
        status='active',
        current_period_start=timestamp - 10000,
        current_period_end=timestamp + 10000,
        items=items_mock
    )

    # Create a customer mock that works with both access patterns
    mock_customer = create_stripe_mock(
        id='cus_def',
        email='customer@example.com'
    )

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
        elif func == stripe.Subscription.retrieve:
            return mock_subscription
        elif func == stripe.Customer.retrieve:
             # Ensure the correct customer ID is passed
             assert args[0] == 'cus_def'
             return mock_customer
        elif func in [stripe.Invoice.retrieve, stripe.Charge.retrieve]:
             raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'sub_456'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is not None
    assert result['id'] == transaction_id
    assert result['object_type'] == 'subscription'
    assert result['customer_id'] == 'cus_def'
    assert result['customer_email'] == 'customer@example.com'
    assert isinstance(result['created_at'], datetime)
    assert 'subscription_data' in result
    assert result['subscription_data']['status'] == 'active'
    assert result['subscription_data']['items'] == [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]

    # Assert asyncio.to_thread was called correctly
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Customer.retrieve, 'cus_def') for call in calls)
    # Check it wasn't called for others after success
    assert not any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)


@pytest.mark.asyncio
async def test_find_transaction_by_id_invoice_success(stripe_service, mocker):
    """Test finding a transaction by ID when it's an Invoice."""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    
    # Create an invoice mock that works with both access patterns
    mock_invoice = create_stripe_mock(
        id='in_789',
        object='invoice',
        amount_paid=2500,
        customer='cus_ghi',
        customer_email='invoice@example.com',
        subscription='sub_xyz',
        created=timestamp
    )

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
        elif func == stripe.Subscription.retrieve:
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        elif func == stripe.Invoice.retrieve:
            return mock_invoice
        elif func == stripe.Charge.retrieve:
             raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'in_789'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is not None
    assert result['id'] == transaction_id
    assert result['object_type'] == 'invoice'
    assert result['amount'] == Decimal('25.00')
    assert result['customer_id'] == 'cus_ghi'
    assert result['customer_email'] == 'invoice@example.com'
    assert result['subscription_id'] == 'sub_xyz'
    assert isinstance(result['created_at'], datetime)

    # Assert asyncio.to_thread was called correctly
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    # Check it wasn't called for Charge after success
    assert not any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


@pytest.mark.asyncio
async def test_find_transaction_by_id_charge_success(stripe_service, mocker):
    """Test finding a transaction by ID when it's a Charge."""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    
    # Create a billing details mock that works with both access patterns
    billing_details_mock = create_stripe_mock(email='charge@example.com')
    
    # Create a charge mock that works with both access patterns
    mock_charge = create_stripe_mock(
        id='ch_abc',
        object='charge',
        amount=1000,
        customer='cus_jkl',
        created=timestamp,
        billing_details=billing_details_mock
    )

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
        elif func == stripe.Subscription.retrieve:
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        elif func == stripe.Invoice.retrieve:
            raise stripe.error.InvalidRequestError('No such invoice', 'id')
        elif func == stripe.Charge.retrieve:
            return mock_charge
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'ch_abc'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is not None
    assert result['id'] == transaction_id
    assert result['object_type'] == 'charge'
    assert result['amount'] == Decimal('10.00')
    assert result['customer_id'] == 'cus_jkl'
    assert result['customer_email'] == 'charge@example.com'
    assert isinstance(result['created_at'], datetime)

    # Assert asyncio.to_thread was called correctly
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


@pytest.mark.asyncio
async def test_find_transaction_by_id_not_found(stripe_service, mocker):
    """Test finding a transaction by ID when it doesn't exist."""
    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    # Configure the mock to raise InvalidRequestError for all expected stripe methods
    async def side_effect_to_thread(func, *args, **kwargs):
        if func in [stripe.PaymentIntent.retrieve, stripe.Subscription.retrieve, stripe.Invoice.retrieve, stripe.Charge.retrieve]:
            raise stripe.error.InvalidRequestError(f'No such {func.__name__.lower()}', 'id')
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'non_existent_id'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is None

    # Assert asyncio.to_thread was called with each stripe method
    calls = mock_to_thread.call_args_list
    assert mock_to_thread.call_count == 4 # Should try all 4 types
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


@pytest.mark.asyncio
async def test_find_transaction_by_id_general_exception(stripe_service, mocker):
    """Test finding a transaction by ID when general exceptions occur during lookups."""
    # Mock asyncio.to_thread to raise a generic Exception for all calls
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        # Raise exceptions for all Stripe API calls
        if func in [stripe.PaymentIntent.retrieve, stripe.Subscription.retrieve,
                   stripe.Invoice.retrieve, stripe.Charge.retrieve]:
            raise Exception(f'Error in {func.__name__}')
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'error_id'
    # The service method catches all exceptions and returns None when no matches are found
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is None
    
    # Verify all four retrieve methods were called
    calls = mock_to_thread.await_args_list
    assert len(calls) == 4
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


# --- Tests for find_transactions_by_email ---

@pytest.mark.asyncio
async def test_find_transactions_by_email_success(stripe_service, mocker):
    """Test finding transactions by email successfully."""
    test_email = 'found@example.com'
    customer_id = 'cus_found'
    timestamp = int(datetime.now(timezone.utc).timestamp())

    # Create customer mock
    mock_customer = create_stripe_mock(id=customer_id)
    mock_customer_list_obj = create_stripe_mock(data=[mock_customer])

    # Create billing details mock
    billing_details_mock = create_stripe_mock(email=test_email)
    
    # Create charge mock
    charge_mock = create_stripe_mock(billing_details=billing_details_mock)
    
    # Create charges mock
    charges_mock = create_stripe_mock(data=[charge_mock])
    
    # Create payment intent mock
    mock_pi = create_stripe_mock(
        id='pi_email_1',
        object='payment_intent',
        amount=3000,
        customer=customer_id,
        created=timestamp - 5000,
        charges=charges_mock
    )
    mock_pi_list_obj = create_stripe_mock(data=[mock_pi])

    # Create items mock
    items_data = [{'id': 'si_email', 'plan': {'id': 'plan_email'}}]
    items_mock = create_stripe_mock(data=items_data)
    
    # Create subscription mock
    mock_sub = create_stripe_mock(
        id='sub_email_1',
        object='subscription',
        customer=customer_id,
        created=timestamp,
        status='active',
        current_period_start=timestamp - 10000,
        current_period_end=timestamp + 10000,
        items=items_mock
    )
    mock_sub_list_obj = create_stripe_mock(data=[mock_sub])

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.Customer.list:
            assert kwargs.get('email') == test_email
            return mock_customer_list_obj
        elif func == stripe.PaymentIntent.list:
            assert kwargs.get('customer') == customer_id
            return mock_pi_list_obj
        elif func == stripe.Subscription.list:
            assert kwargs.get('customer') == customer_id
            return mock_sub_list_obj
        else:
             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 2
    # Results should be sorted by created_at desc, so subscription comes first
    assert results[0]['id'] == 'sub_email_1'
    assert results[0]['object_type'] == 'subscription'
    assert results[0]['customer_email'] == test_email
    assert results[1]['id'] == 'pi_email_1'
    assert results[1]['object_type'] == 'payment_intent'
    assert results[1]['amount'] == Decimal('30.00')
    assert results[1]['customer_email'] == test_email

    # Assert asyncio.to_thread calls
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.Customer.list, email=test_email, limit=5) for call in calls)
    assert any(call == mocker.call(stripe.PaymentIntent.list, customer=customer_id, limit=10) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.list, customer=customer_id, limit=10) for call in calls)


@pytest.mark.asyncio
async def test_find_transactions_by_email_no_customer(stripe_service, mocker):
    """Test finding transactions when no customer matches the email."""
    test_email = 'notfound@example.com'
    mock_customer_list_obj = MagicMock(data=[])

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.Customer.list:
            assert kwargs.get('email') == test_email
            return mock_customer_list_obj
        # Other list calls should not happen
        elif func in [stripe.PaymentIntent.list, stripe.Subscription.list]:
             raise AssertionError(f"Should not have called {func.__name__}")
        else:
             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    mock_to_thread.assert_awaited_once_with(stripe.Customer.list, email=test_email, limit=5)


@pytest.mark.asyncio
async def test_find_transactions_by_email_customer_no_transactions(stripe_service, mocker):
    """Test finding transactions when customer exists but has no transactions."""
    test_email = 'no_trans@example.com'
    customer_id = 'cus_no_trans'

    mock_customer = MagicMock(id=customer_id)
    mock_customer_list_obj = MagicMock(data=[mock_customer])
    mock_pi_list_obj = MagicMock(data=[])
    mock_sub_list_obj = MagicMock(data=[])

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.Customer.list:
            return mock_customer_list_obj
        elif func == stripe.PaymentIntent.list:
            return mock_pi_list_obj
        elif func == stripe.Subscription.list:
            return mock_sub_list_obj
        else:
             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.Customer.list, email=test_email, limit=5) for call in calls)
    assert any(call == mocker.call(stripe.PaymentIntent.list, customer=customer_id, limit=10) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.list, customer=customer_id, limit=10) for call in calls)


@pytest.mark.asyncio
async def test_find_transactions_by_email_exception(stripe_service, mocker):
    """Test finding transactions by email when an exception occurs during customer lookup."""
    test_email = 'error@example.com'

    # Mock asyncio.to_thread to raise exception on Customer.list
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.Customer.list:
            raise Exception('API Error during customer list')
        else:
             raise AssertionError("Should not have called other methods after exception")

    mock_to_thread.side_effect = side_effect_to_thread

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    mock_to_thread.assert_awaited_once_with(stripe.Customer.list, email=test_email, limit=5)


# --- Tests for analyze_transaction ---

@pytest.mark.asyncio
async def test_analyze_transaction_payment_intent(stripe_service, mocker):
    """Test analyzing a PaymentIntent transaction."""
    transaction_data = {
        "id": "pi_analyze_1",
        "object_type": "payment_intent",
        "amount": Decimal('15.99'),
        "customer_id": "cus_analyze_pi",
        "customer_email": "analyze_pi@example.com",
        "created_at": datetime.now(timezone.utc)
    }

    # Create metadata mock
    metadata_mock = create_stripe_mock(product_id="prod_abc")
    
    # Create payment intent mock with metadata
    mock_payment_intent = create_stripe_mock(
        id="pi_analyze_1",
        metadata=metadata_mock
    )

    # Mock asyncio.to_thread for the retrieve call inside analyze_transaction
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_analyze(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            assert args[0] == "pi_analyze_1"
            assert kwargs.get('expand') == ["metadata"]
            return mock_payment_intent
        else:
            raise NotImplementedError(f"Unexpected call in analyze_transaction: {func.__name__}")

    mock_to_thread.side_effect = side_effect_analyze

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'oneoff'
    assert result['recurring'] is False
    assert result['amount'] == Decimal('15.99')
    assert result['product_id'] == 'prod_abc'
    assert result['transaction_id'] == 'pi_analyze_1'
    mock_to_thread.assert_awaited_once_with(stripe.PaymentIntent.retrieve, "pi_analyze_1", expand=["metadata"])


@pytest.mark.asyncio
async def test_analyze_transaction_subscription(stripe_service, mocker):
    """Test analyzing a Subscription transaction."""
    now = datetime.now(timezone.utc)
    start_ts = int(now.timestamp()) - 1000
    end_ts = int(now.timestamp()) + 2000
    created_ts = int(now.timestamp()) - 5000

    transaction_data = {
        "id": "sub_analyze_1",
        "object_type": "subscription",
        "customer_id": "cus_analyze_sub",
        "customer_email": "analyze_sub@example.com",
        "created_at": datetime.fromtimestamp(created_ts, timezone.utc),
        "subscription_data": {
            "status": "active",
            "current_period_start": datetime.fromtimestamp(start_ts, timezone.utc),
            "current_period_end": datetime.fromtimestamp(end_ts, timezone.utc),
            "items": [
                {
                    "id": "si_analyze",
                    "plan": {
                        "id": "plan_analyze",
                        "product": "prod_analyze",
                        "amount": 999 # Cents
                    }
                }
            ]
        }
    }

    # Mock asyncio.to_thread - it shouldn't be called for this type if data is present
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'subscription'
    assert result['recurring'] is True
    assert result['amount'] == Decimal('9.99')
    assert result['subscription_id'] == 'sub_analyze_1'
    assert result['plan_id'] == 'plan_analyze'
    assert result['product_id'] == 'prod_analyze'
    mock_to_thread.assert_not_awaited() # No API calls expected


@pytest.mark.asyncio
async def test_analyze_transaction_invoice_for_subscription(stripe_service, mocker):
    """Test analyzing an Invoice transaction linked to a subscription."""
    transaction_data = {
        "id": "in_analyze_sub",
        "object_type": "invoice",
        "amount": Decimal('49.50'),
        "customer_id": "cus_analyze_inv_sub",
        "customer_email": "analyze_inv_sub@example.com",
        "subscription_id": "sub_linked",
        "created_at": datetime.now(timezone.utc)
    }

    # Create plan data
    plan_data = {
        "id": "plan_linked",
        "product": "prod_linked",
        "amount": 4950
    }
    
    # Create item data
    item_data = {
        "id": "si_linked",
        "plan": plan_data
    }
    
    # Create items mock
    items_mock = create_stripe_mock(data=[item_data])
    
    # Create subscription mock
    mock_subscription = create_stripe_mock(
        id="sub_linked",
        items=items_mock
    )
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_analyze(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_linked"
            return mock_subscription
        else:
            raise NotImplementedError(f"Unexpected call in analyze_transaction: {func.__name__}")

    mock_to_thread.side_effect = side_effect_analyze

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'subscription'
    assert result['recurring'] is True
    assert result['amount'] == Decimal('49.50')
    assert result['subscription_id'] == 'sub_linked'
    assert result['plan_id'] == 'plan_linked'
    assert result['product_id'] == 'prod_linked'
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.retrieve, 'sub_linked')


@pytest.mark.asyncio
async def test_analyze_transaction_invoice_one_off(stripe_service, mocker):
    """Test analyzing an Invoice transaction not linked to a subscription."""
    transaction_data = {
        "id": "in_analyze_oneoff",
        "object_type": "invoice",
        "amount": Decimal('100.00'),
        "customer_id": "cus_analyze_inv_oneoff",
        "customer_email": "analyze_inv_oneoff@example.com",
        "subscription_id": None, # Explicitly None
        "created_at": datetime.now(timezone.utc)
    }

    # Mock asyncio.to_thread - it shouldn't be called
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'oneoff'
    assert result['recurring'] is False
    assert result['amount'] == Decimal('100.00')
    assert result['subscription_id'] is None
    mock_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_transaction_unknown_type(stripe_service, mocker):
    """Test analyzing a transaction with an unknown object type."""
    transaction_data = {
        "id": "unknown_123",
        "object_type": "charge", # Example of a type not explicitly handled for plan/product
        "amount": Decimal('5.00'),
        "customer_id": "cus_unknown",
        "customer_email": "unknown@example.com",
        "created_at": datetime.now(timezone.utc)
    }

    # Mock asyncio.to_thread - it shouldn't be called
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'unknown' # Default value
    assert result['recurring'] is False
    assert result['amount'] == Decimal('0.00') # Default value
    assert result['transaction_id'] == 'unknown_123'
    mock_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_transaction_exception(stripe_service, mocker):
    """Test analyze_transaction when an internal exception occurs during API call."""
    transaction_data = {
        "id": "pi_analyze_err",
        "object_type": "payment_intent",
        "amount": Decimal('15.99'),
        "customer_id": "cus_analyze_err",
        "customer_email": "analyze_err@example.com",
        "created_at": datetime.now(timezone.utc)
    }

    # Mock asyncio.to_thread to raise exception
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_analyze_err(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise Exception('API Error during analysis')
        else:
            raise NotImplementedError("Should only call retrieve PI")

    mock_to_thread.side_effect = side_effect_analyze_err

    # The service method logs the exception but doesn't re-raise it
    result = await stripe_service.analyze_transaction(transaction_data)
    
    # Verify the result contains default values
    assert result['transaction_type'] == 'oneoff'
    assert result['amount'] == Decimal('15.99')  # Should preserve the original amount
    assert result['product_id'] is None  # Product ID lookup failed

    mock_to_thread.assert_awaited_once_with(stripe.PaymentIntent.retrieve, "pi_analyze_err", expand=["metadata"])


# --- Tests for handle_subscription_renewal ---

@pytest.mark.asyncio
async def test_handle_subscription_renewal_success(stripe_service, mocker):
    """Test handling a subscription renewal successfully."""
    subscription_id = 'sub_renew_ok'
    mock_subscription = MagicMock(id=subscription_id)

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_renewal(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == subscription_id
            return mock_subscription
        else:
            raise NotImplementedError("Should only call retrieve Subscription")

    mock_to_thread.side_effect = side_effect_renewal

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is True
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.retrieve, subscription_id)


@pytest.mark.asyncio
async def test_handle_subscription_renewal_not_found(stripe_service, mocker):
    """Test handling renewal when the subscription is not found."""
    subscription_id = 'sub_renew_404'

    # Mock asyncio.to_thread to raise InvalidRequestError
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_renewal_404(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == subscription_id
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        else:
            raise NotImplementedError("Should only call retrieve Subscription")

    mock_to_thread.side_effect = side_effect_renewal_404

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is False # Service method catches the error and returns False
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.retrieve, subscription_id)


@pytest.mark.asyncio
async def test_handle_subscription_renewal_exception(stripe_service, mocker):
    """Test handling renewal when a general exception occurs during retrieval."""
    subscription_id = 'sub_renew_err'

    # Mock asyncio.to_thread to raise a generic exception
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_renewal_err(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == subscription_id
            raise Exception('API Error')
        else:
            raise NotImplementedError("Should only call retrieve Subscription")

    mock_to_thread.side_effect = side_effect_renewal_err

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is False # Service method catches the error and returns False
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.retrieve, subscription_id)


# --- Tests for cancel_subscription ---

@pytest.mark.asyncio
async def test_cancel_subscription_success(stripe_service, mocker):
    """Test cancelling a subscription successfully."""
    subscription_id = 'sub_cancel_ok'
    mock_result = MagicMock()
    # Set the attribute directly on the mock
    mock_result.cancel_at_period_end = True

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_cancel(func, *args, **kwargs):
        if func == stripe.Subscription.modify:
            assert args[0] == subscription_id
            assert kwargs.get('cancel_at_period_end') is True
            return mock_result
        else:
            raise NotImplementedError("Should only call modify Subscription")

    mock_to_thread.side_effect = side_effect_cancel

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is True
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.modify, subscription_id, cancel_at_period_end=True)


@pytest.mark.asyncio
async def test_cancel_subscription_failure(stripe_service, mocker):
    """Test cancelling a subscription when Stripe doesn't confirm cancellation."""
    subscription_id = 'sub_cancel_fail'
    # Simulate Stripe returning something unexpected or False for cancel_at_period_end
    mock_result = create_stripe_mock(cancel_at_period_end=False)

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_cancel_fail(func, *args, **kwargs):
        if func == stripe.Subscription.modify:
            assert args[0] == subscription_id
            assert kwargs.get('cancel_at_period_end') is True
            return mock_result # Return the mock indicating failure
        else:
            raise NotImplementedError("Should only call modify Subscription")

    mock_to_thread.side_effect = side_effect_cancel_fail

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.modify, subscription_id, cancel_at_period_end=True)


@pytest.mark.asyncio
async def test_cancel_subscription_not_found(stripe_service, mocker):
    """Test cancelling a subscription that is not found."""
    subscription_id = 'sub_cancel_404'

    # Mock asyncio.to_thread to raise InvalidRequestError
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_cancel_404(func, *args, **kwargs):
        if func == stripe.Subscription.modify:
            assert args[0] == subscription_id
            assert kwargs.get('cancel_at_period_end') is True
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        else:
            raise NotImplementedError("Should only call modify Subscription")

    mock_to_thread.side_effect = side_effect_cancel_404

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False # Service method catches the error
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.modify, subscription_id, cancel_at_period_end=True)


@pytest.mark.asyncio
async def test_cancel_subscription_exception(stripe_service, mocker):
    """Test cancelling a subscription when a general exception occurs."""
    subscription_id = 'sub_cancel_err'

    # Mock asyncio.to_thread to raise a generic exception
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_cancel_err(func, *args, **kwargs):
        if func == stripe.Subscription.modify:
            assert args[0] == subscription_id
            assert kwargs.get('cancel_at_period_end') is True
            raise Exception('API Error')
        else:
            raise NotImplementedError("Should only call modify Subscription")

    mock_to_thread.side_effect = side_effect_cancel_err

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False # Service method catches the error
    mock_to_thread.assert_awaited_once_with(stripe.Subscription.modify, subscription_id, cancel_at_period_end=True)

# --- Tests for cancel_user_subscription ---

@pytest.mark.asyncio
async def test_cancel_user_subscription_success(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock, 
    mock_user_active_db_subscription: MagicMock,
    mock_datetime_now: datetime,
    mocker: MagicMock
):
    """Test successful subscription cancellation at period end."""
    user_id = "user_123"
    stripe_sub_id = mock_user_active_db_subscription.stripe_subscription_id
    
    # Configure DB mock to return the active subscription
    mock_db_session.scalars.return_value.first.return_value = mock_user_active_db_subscription
    
    # Mock Stripe API calls
    mock_retrieved_stripe_sub = create_mock_stripe_subscription(
        id=stripe_sub_id, status="active", cancel_at_period_end=False
    )
    mock_updated_stripe_sub = create_mock_stripe_subscription(
        id=stripe_sub_id, status="active", cancel_at_period_end=True, current_period_end=int(mock_datetime_now.timestamp() + 3600) # e.g. 1 hour later
    )
    
    mocker.patch('stripe.Subscription.retrieve', return_value=mock_retrieved_stripe_sub)
    mocker.patch('stripe.Subscription.update', return_value=mock_updated_stripe_sub)
    
    result = await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
    
    # Assertions
    stripe.Subscription.retrieve.assert_called_once_with(stripe_sub_id)
    stripe.Subscription.update.assert_called_once_with(stripe_sub_id, cancel_at_period_end=True)
    
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(mock_user_active_db_subscription)
    
    assert mock_user_active_db_subscription.updated_at == mock_datetime_now
    
    expected_period_end_dt = datetime.fromtimestamp(mock_updated_stripe_sub.current_period_end, tz=timezone.utc)
    assert result == {
        "stripe_subscription_id": stripe_sub_id,
        "subscription_status": "active", # Stripe status is still active
        "period_end_date": expected_period_end_dt.isoformat()
    }

@pytest.mark.asyncio
async def test_cancel_user_subscription_already_set_to_cancel(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock, 
    mock_user_active_db_subscription: MagicMock,
    mocker: MagicMock
):
    """Test when subscription is already set to cancel at period end on Stripe."""
    user_id = "user_123"
    stripe_sub_id = mock_user_active_db_subscription.stripe_subscription_id
    
    mock_db_session.scalars.return_value.first.return_value = mock_user_active_db_subscription
    
    mock_retrieved_stripe_sub = create_mock_stripe_subscription(
        id=stripe_sub_id, status="active", cancel_at_period_end=True, current_period_end=1234567890
    )
    mocker.patch('stripe.Subscription.retrieve', return_value=mock_retrieved_stripe_sub)
    mock_stripe_update = mocker.patch('stripe.Subscription.update') # Should not be called
    
    result = await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
    
    stripe.Subscription.retrieve.assert_called_once_with(stripe_sub_id)
    mock_stripe_update.assert_not_called()
    mock_db_session.commit.assert_not_called() # No DB change in this specific path in service
    
    expected_period_end_dt = datetime.fromtimestamp(mock_retrieved_stripe_sub.current_period_end, tz=timezone.utc)
    assert result == {
        "stripe_subscription_id": stripe_sub_id,
        "subscription_status": "active",
        "period_end_date": expected_period_end_dt.isoformat()
    }

@pytest.mark.asyncio
async def test_cancel_user_subscription_already_canceled_stripe(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock, 
    mock_user_active_db_subscription: MagicMock,
    mock_datetime_now: datetime,
    mocker: MagicMock
):
    """Test when subscription is already 'canceled' on Stripe."""
    user_id = "user_123"
    stripe_sub_id = mock_user_active_db_subscription.stripe_subscription_id
    
    # Simulate DB subscription is 'active' initially
    mock_user_active_db_subscription.status = "active"
    mock_db_session.scalars.return_value.first.return_value = mock_user_active_db_subscription
    
    mock_retrieved_stripe_sub = create_mock_stripe_subscription(id=stripe_sub_id, status="canceled")
    mocker.patch('stripe.Subscription.retrieve', return_value=mock_retrieved_stripe_sub)
    
    with pytest.raises(HTTPException) as exc_info:
        await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
        
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Subscription is already canceled."
    
    stripe.Subscription.retrieve.assert_called_once_with(stripe_sub_id)
    # Check if DB was updated to 'canceled'
    assert mock_user_active_db_subscription.status == "canceled"
    assert mock_user_active_db_subscription.updated_at == mock_datetime_now
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(mock_user_active_db_subscription)

@pytest.mark.asyncio
async def test_cancel_user_subscription_stripe_api_error_on_update(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock, 
    mock_user_active_db_subscription: MagicMock,
    mocker: MagicMock
):
    """Test handling Stripe API error during Subscription.update."""
    user_id = "user_123"
    stripe_sub_id = mock_user_active_db_subscription.stripe_subscription_id
    
    mock_db_session.scalars.return_value.first.return_value = mock_user_active_db_subscription
    
    mock_retrieved_stripe_sub = create_mock_stripe_subscription(id=stripe_sub_id, status="active", cancel_at_period_end=False)
    mocker.patch('stripe.Subscription.retrieve', return_value=mock_retrieved_stripe_sub)
    mocker.patch('stripe.Subscription.update', side_effect=stripe.error.StripeError("Stripe API failed"))
    
    with pytest.raises(HTTPException) as exc_info:
        await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
        
    assert exc_info.value.status_code == 500
    assert "Stripe API error: Stripe API failed" in exc_info.value.detail
    
    stripe.Subscription.retrieve.assert_called_once_with(stripe_sub_id)
    stripe.Subscription.update.assert_called_once_with(stripe_sub_id, cancel_at_period_end=True)
    mock_db_session.commit.assert_not_called() # Should not commit if Stripe update fails

@pytest.mark.asyncio
async def test_cancel_user_subscription_stripe_resource_missing_on_retrieve(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock, 
    mock_user_active_db_subscription: MagicMock,
    mocker: MagicMock
):
    """Test handling Stripe resource_missing error during Subscription.retrieve."""
    user_id = "user_123"
    # DB subscription exists
    mock_db_session.scalars.return_value.first.return_value = mock_user_active_db_subscription 
    
    # Stripe.retrieve raises resource_missing
    mocker.patch('stripe.Subscription.retrieve', side_effect=stripe.error.InvalidRequestError("No such subscription", "id", code="resource_missing"))
    
    with pytest.raises(HTTPException) as exc_info:
        await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
        
    assert exc_info.value.status_code == 404 # Service maps this to 404
    assert exc_info.value.detail == "Subscription not found on Stripe."
    
    stripe.Subscription.retrieve.assert_called_once_with(mock_user_active_db_subscription.stripe_subscription_id)
    mock_db_session.commit.assert_not_called()

@pytest.mark.asyncio
async def test_cancel_user_subscription_db_not_found_error(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock
):
    """Test when no active subscription is found in the database."""
    user_id = "user_non_existent_sub"
    mock_db_session.scalars.return_value.first.return_value = None # Simulate no subscription found
    
    with pytest.raises(HTTPException) as exc_info:
        await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
        
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No active subscription found to cancel."
    
    # Ensure execute was called to query DB
    mock_db_session.execute.assert_called_once() 

@pytest.mark.asyncio
async def test_cancel_user_subscription_db_subscription_missing_stripe_id(
    stripe_service_with_db: StripeService, 
    mock_db_session: AsyncMock,
    mocker: MagicMock
):
    """Test when DB subscription record is missing stripe_subscription_id."""
    user_id = "user_missing_stripe_id"
    
    # Create a mock subscription that's missing the stripe_subscription_id
    db_sub_no_stripe_id = MagicMock(spec=SubscriptionModel)
    db_sub_no_stripe_id.id = "db_sub_no_stripe"
    db_sub_no_stripe_id.user_id = user_id
    db_sub_no_stripe_id.stripe_subscription_id = None # Key part: missing Stripe ID
    db_sub_no_stripe_id.status = "active"
    
    mock_db_session.scalars.return_value.first.return_value = db_sub_no_stripe_id
    
    # We expect the service to raise a DatabaseError, which gets mapped to HTTP 500
    # The original DatabaseError is raised from _get_user_active_subscription_from_db
    # and then caught and re-raised as HTTPException in cancel_user_subscription
    
    # Mock the logger to prevent actual logging during test
    mocker.patch('app.services.stripe_service.logger')

    with pytest.raises(HTTPException) as exc_info:
        await stripe_service_with_db.cancel_user_subscription(user_id=user_id)
        
    assert exc_info.value.status_code == 500 
    # The detail comes from the re-raised HTTPException in cancel_user_subscription
    # which wraps the CoreDatabaseError from _get_user_active_subscription_from_db
    assert "Database error: Subscription record is missing Stripe ID." in exc_info.value.detail
    
    mock_db_session.execute.assert_called_once()
    # Stripe API should not be called if DB record is faulty
    mocker.patch('stripe.Subscription.retrieve').assert_not_called()
