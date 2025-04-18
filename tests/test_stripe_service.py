import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import asyncio # Ensure asyncio is imported

from app.services.stripe_service import StripeService
from app.core.config import settings
import stripe  # Import stripe to potentially mock its exceptions

@pytest.fixture
def stripe_service():
    """Fixture to create a StripeService instance in test mode."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
        # Initialize with test_mode=True to skip API key validation if needed
        service = StripeService(test_mode=True)
        return service

# --- Tests for find_transaction_by_id ---

@pytest.mark.asyncio
async def test_find_transaction_by_id_payment_intent_success(stripe_service, mocker):
    """Test finding a transaction by ID when it's a PaymentIntent."""
    mock_payment_intent = MagicMock()
    mock_payment_intent.id = 'pi_123'
    mock_payment_intent.object = 'payment_intent'
    mock_payment_intent.amount = 5000
    mock_payment_intent.customer = 'cus_abc'
    mock_payment_intent.created = int(datetime.now(timezone.utc).timestamp())
    mock_payment_intent.charges = MagicMock()
    mock_payment_intent.charges.data = [
        MagicMock(billing_details=MagicMock(email='test@example.com'))
    ]

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
    mock_subscription = MagicMock()
    mock_subscription.id = 'sub_456'
    mock_subscription.object = 'subscription'
    mock_subscription.customer = 'cus_def'
    mock_subscription.created = int(datetime.now(timezone.utc).timestamp())
    mock_subscription.status = 'active'
    mock_subscription.current_period_start = int(datetime.now(timezone.utc).timestamp()) - 10000
    mock_subscription.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 10000
    mock_subscription.items = MagicMock()
    mock_subscription.items.data = [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]

    mock_customer = MagicMock()
    mock_customer.email = 'customer@example.com'

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
    mock_invoice = MagicMock()
    mock_invoice.id = 'in_789'
    mock_invoice.object = 'invoice'
    mock_invoice.amount_paid = 2500
    mock_invoice.customer = 'cus_ghi'
    mock_invoice.customer_email = 'invoice@example.com'
    mock_invoice.subscription = 'sub_xyz'
    mock_invoice.created = int(datetime.now(timezone.utc).timestamp())

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
    mock_charge = MagicMock()
    mock_charge.id = 'ch_abc'
    mock_charge.object = 'charge'
    mock_charge.amount = 1000
    mock_charge.customer = 'cus_jkl'
    mock_charge.created = int(datetime.now(timezone.utc).timestamp())
    mock_charge.billing_details = MagicMock(email='charge@example.com')

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
    """Test finding a transaction by ID when a general exception occurs during the first lookup."""
    # Mock asyncio.to_thread to raise a generic Exception on the first expected call
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    async def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise Exception('Something went wrong')
        # These should not be reached if the first call raises an exception that bubbles up
        elif func in [stripe.Subscription.retrieve, stripe.Invoice.retrieve, stripe.Charge.retrieve]:
             raise AssertionError("Should not have called other stripe methods after exception")
        else:
            raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    mock_to_thread.side_effect = side_effect_to_thread

    transaction_id = 'error_id'
    # The service method catches the exception and logs it, returning None
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is None
    # Assert asyncio.to_thread was called only with the first stripe method
    mock_to_thread.assert_awaited_once_with(stripe.PaymentIntent.retrieve, transaction_id)


# --- Tests for find_transactions_by_email ---

@pytest.mark.asyncio
async def test_find_transactions_by_email_success(stripe_service, mocker):
    """Test finding transactions by email successfully."""
    test_email = 'found@example.com'
    customer_id = 'cus_found'

    mock_customer = MagicMock(id=customer_id)
    mock_customer_list_obj = MagicMock(data=[mock_customer])

    mock_pi = MagicMock()
    mock_pi.id = 'pi_email_1'
    mock_pi.object = 'payment_intent'
    mock_pi.amount = 3000
    mock_pi.customer = customer_id
    mock_pi.created = int(datetime.now(timezone.utc).timestamp()) - 5000
    mock_pi.charges = MagicMock(data=[MagicMock(billing_details=MagicMock(email=test_email))])
    mock_pi_list_obj = MagicMock(data=[mock_pi])

    mock_sub = MagicMock()
    mock_sub.id = 'sub_email_1'
    mock_sub.object = 'subscription'
    mock_sub.customer = customer_id
    mock_sub.created = int(datetime.now(timezone.utc).timestamp())
    mock_sub.status = 'active'
    mock_sub.current_period_start = int(datetime.now(timezone.utc).timestamp()) - 10000
    mock_sub.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 10000
    mock_sub.items = MagicMock(data=[{'id': 'si_email', 'plan': {'id': 'plan_email'}}])
    mock_sub_list_obj = MagicMock(data=[mock_sub])

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

    # Mock the retrieve call within analyze_transaction
    mock_payment_intent = MagicMock()
    mock_payment_intent.metadata = {"product_id": "prod_abc"}

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

    # Mock the Subscription retrieve call via asyncio.to_thread
    mock_subscription = MagicMock()
    mock_subscription.items = MagicMock()
    mock_subscription.items.data = [
        {
            "id": "si_linked",
            "plan": {
                "id": "plan_linked",
                "product": "prod_linked",
                "amount": 4950
            }
        }
    ]
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

    # The service method should catch the exception and re-raise it
    with pytest.raises(Exception, match='API Error during analysis'):
        await stripe_service.analyze_transaction(transaction_data)

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
    mock_result = MagicMock()
    mock_result.cancel_at_period_end = False # Simulate failure case

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
