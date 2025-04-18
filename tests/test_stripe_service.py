import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone

from app.services.stripe_service import StripeService
from app.core.config import settings
import stripe  # Import stripe to potentially mock its exceptions

# TODO: Add test cases here

@pytest.fixture
def stripe_service():
    """Fixture to create a StripeService instance in test mode."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
        service = StripeService(test_mode=True) # Use test_mode=True if init checks keys
        # If init doesn't check keys, test_mode=False might be needed depending on stripe lib behavior
        # service = StripeService(test_mode=False)
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
    # and raise exceptions for other stripe methods
    def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            return mock_payment_intent
        elif func == stripe.Subscription.retrieve:
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        elif func == stripe.Invoice.retrieve:
            raise stripe.error.InvalidRequestError('No such invoice', 'id')
        elif func == stripe.Charge.retrieve:
            raise stripe.error.InvalidRequestError('No such charge', 'id')
        else:
            # Fallback for unexpected calls
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

    # Assert asyncio.to_thread was called with the correct stripe method and arguments
    mock_to_thread.assert_awaited_with(stripe.PaymentIntent.retrieve, transaction_id)
    # We don't assert on the number of calls to to_thread here, as the method
    # tries different types sequentially. We'll check the specific calls made
    # within the side_effect or by inspecting call_args_list if needed for more complex scenarios.

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
    mock_subscription.items.data = [{'id': 'si_1', 'plan': {'id': 'plan_1'}}] # Example item data

    mock_customer = MagicMock()
    mock_customer.email = 'customer@example.com'

    # Mock asyncio.to_thread
    mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)

    # Configure the mock to return the mock_subscription when called with stripe.Subscription.retrieve
    # and raise exceptions for other stripe methods, and return mock_customer for stripe.Customer.retrieve
    def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
        elif func == stripe.Subscription.retrieve:
            return mock_subscription
        elif func == stripe.Customer.retrieve:
            return mock_customer
        elif func == stripe.Invoice.retrieve:
            raise stripe.error.InvalidRequestError('No such invoice', 'id')
        elif func == stripe.Charge.retrieve:
            raise stripe.error.InvalidRequestError('No such charge', 'id')
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
    # Assert asyncio.to_thread was called with the correct stripe methods and arguments
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Customer.retrieve, 'cus_def') for call in calls)
    # Ensure other retrieves were attempted but failed as expected by the side_effect
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)

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

    # Configure the mock to return the mock_invoice when called with stripe.Invoice.retrieve
    # and raise exceptions for other stripe methods
    def side_effect_to_thread(func, *args, **kwargs):
        if func == stripe.PaymentIntent.retrieve:
            raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
        elif func == stripe.Subscription.retrieve:
            raise stripe.error.InvalidRequestError('No such subscription', 'id')
        elif func == stripe.Invoice.retrieve:
            return mock_invoice
        elif func == stripe.Charge.retrieve:
            raise stripe.error.InvalidRequestError('No such charge', 'id')
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

    # Assert asyncio.to_thread was called with the correct stripe methods and arguments
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    # Ensure Charge retrieve was attempted but failed as expected by the side_effect
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)

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

    # Configure the mock to return the mock_charge when called with stripe.Charge.retrieve
    # and raise exceptions for other stripe methods
    def side_effect_to_thread(func, *args, **kwargs):
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

    # Assert asyncio.to_thread was called with the correct stripe methods and arguments
    calls = mock_to_thread.call_args_list
    assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
    assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)

@pytest.mark.asyncio
async def test_find_transaction_by_id_not_found(stripe_service, mocker):
    """Test finding a transaction by ID when it doesn't exist."""
    # Mock all retrieves to fail
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such payment_intent', 'id'))
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such subscription', 'id'))
    mock_retrieve_inv = mocker.patch('stripe.Invoice.retrieve', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such invoice', 'id'))
    mock_retrieve_ch = mocker.patch('stripe.Charge.retrieve', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such charge', 'id'))

    transaction_id = 'non_existent_id'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is None

    mock_retrieve_pi.assert_awaited_once_with(transaction_id)
    mock_retrieve_sub.assert_awaited_once_with(transaction_id)

@pytest.mark.asyncio
async def test_find_transactions_by_email_success(stripe_service, mocker):
    """Test finding transactions by email successfully."""
    test_email = 'found@example.com'
    customer_id = 'cus_found'

    mock_customer = MagicMock(id=customer_id)
    mock_customer_list = MagicMock(data=[mock_customer])

    mock_pi = MagicMock()
    mock_pi.id = 'pi_email_1'
    mock_pi.object = 'payment_intent'
    mock_pi.amount = 3000
    mock_pi.customer = customer_id
    mock_pi.created = int(datetime.now(timezone.utc).timestamp()) - 5000
    mock_pi.charges = MagicMock(data=[MagicMock(billing_details=MagicMock(email=test_email))])
    mock_pi_list = MagicMock(data=[mock_pi])

    mock_sub = MagicMock()
    mock_sub.id = 'sub_email_1'
    mock_sub.object = 'subscription'
    mock_sub.customer = customer_id
    mock_sub.created = int(datetime.now(timezone.utc).timestamp())
    mock_sub.status = 'active'
    mock_sub.current_period_start = int(datetime.now(timezone.utc).timestamp()) - 10000
    mock_sub.current_period_end = int(datetime.now(timezone.utc).timestamp()) + 10000
    mock_sub.items = MagicMock(data=[{'id': 'si_email', 'plan': {'id': 'plan_email'}}])
    mock_sub_list = MagicMock(data=[mock_sub])

    # Mock Stripe API calls
    mock_list_cus = mocker.patch('stripe.Customer.list', new_callable=AsyncMock, return_value=mock_customer_list)
    mock_list_pi = mocker.patch('stripe.PaymentIntent.list', new_callable=AsyncMock, return_value=mock_pi_list)
    mock_list_sub = mocker.patch('stripe.Subscription.list', new_callable=AsyncMock, return_value=mock_sub_list)

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

    mock_list_cus.assert_awaited_once_with(email=test_email, limit=5)
    mock_list_pi.assert_awaited_once_with(customer=customer_id, limit=10)
    mock_list_sub.assert_awaited_once_with(customer=customer_id, limit=10)

@pytest.mark.asyncio
async def test_find_transactions_by_email_no_customer(stripe_service, mocker):
    """Test finding transactions when no customer matches the email."""
    test_email = 'notfound@example.com'
    mock_customer_list = MagicMock(data=[])

    # Mock Stripe API calls
    mock_list_cus = mocker.patch('stripe.Customer.list', new_callable=AsyncMock, return_value=mock_customer_list)
    mock_list_pi = mocker.patch('stripe.PaymentIntent.list', new_callable=AsyncMock)
    mock_list_sub = mocker.patch('stripe.Subscription.list', new_callable=AsyncMock)

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    mock_list_cus.assert_awaited_once_with(email=test_email, limit=5)
    mock_list_pi.assert_not_awaited()
    mock_list_sub.assert_not_awaited()

@pytest.mark.asyncio
async def test_find_transactions_by_email_customer_no_transactions(stripe_service, mocker):
    """Test finding transactions when customer exists but has no transactions."""
    test_email = 'no_trans@example.com'
    customer_id = 'cus_no_trans'

    mock_customer = MagicMock(id=customer_id)
    mock_customer_list = MagicMock(data=[mock_customer])
    mock_pi_list = MagicMock(data=[])
    mock_sub_list = MagicMock(data=[])

    # Mock Stripe API calls
    mock_list_cus = mocker.patch('stripe.Customer.list', new_callable=AsyncMock, return_value=mock_customer_list)
    mock_list_pi = mocker.patch('stripe.PaymentIntent.list', new_callable=AsyncMock, return_value=mock_pi_list)
    mock_list_sub = mocker.patch('stripe.Subscription.list', new_callable=AsyncMock, return_value=mock_sub_list)

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    mock_list_cus.assert_awaited_once_with(email=test_email, limit=5)
    mock_list_pi.assert_awaited_once_with(customer=customer_id, limit=10)

# Note: _format_transaction is tested implicitly via analyze_transaction

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
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock, return_value=mock_payment_intent)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'oneoff'
    assert result['recurring'] is False
    assert result['amount'] == Decimal('15.99')
    assert result['customer_id'] == 'cus_analyze_pi'
    assert result['customer_email'] == 'analyze_pi@example.com'
    assert result['subscription_id'] is None
    assert result['plan_id'] is None
    assert result['product_id'] == 'prod_abc' # From mocked metadata
    assert result['transaction_id'] == 'pi_analyze_1'
    assert isinstance(result['created_at'], datetime)
    mock_retrieve_pi.assert_awaited_once_with("pi_analyze_1", expand=["metadata"])

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

    # No extra API calls expected for subscription type if data is present
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock)
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'subscription'
    assert result['recurring'] is True
    assert result['amount'] == Decimal('9.99') # Calculated from plan amount
    assert result['customer_id'] == 'cus_analyze_sub'
    assert result['customer_email'] == 'analyze_sub@example.com'
    assert result['subscription_id'] == 'sub_analyze_1'
    assert result['plan_id'] == 'plan_analyze'
    assert result['product_id'] == 'prod_analyze'
    assert result['transaction_id'] == 'sub_analyze_1'
    assert result['created_at'] == datetime.fromtimestamp(created_ts, timezone.utc)

    mock_retrieve_pi.assert_not_awaited()
    mock_retrieve_sub.assert_not_awaited()

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

    # Mock the Subscription retrieve call
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
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock, return_value=mock_subscription)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'subscription'
    assert result['recurring'] is True
    assert result['amount'] == Decimal('49.50') # Amount from invoice data
    assert result['customer_id'] == 'cus_analyze_inv_sub'
    assert result['customer_email'] == 'analyze_inv_sub@example.com'
    assert result['subscription_id'] == 'sub_linked'
    assert result['plan_id'] == 'plan_linked' # From mocked subscription
    assert result['product_id'] == 'prod_linked' # From mocked subscription
    assert result['transaction_id'] == 'in_analyze_sub'
    assert isinstance(result['created_at'], datetime)

    mock_retrieve_sub.assert_awaited_once_with('sub_linked')

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

    # No extra API calls expected
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock)

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'oneoff'
    assert result['recurring'] is False
    assert result['amount'] == Decimal('100.00')
    assert result['customer_id'] == 'cus_analyze_inv_oneoff'
    assert result['customer_email'] == 'analyze_inv_oneoff@example.com'
    assert result['subscription_id'] is None
    assert result['plan_id'] is None
    assert result['product_id'] is None
    assert result['transaction_id'] == 'in_analyze_oneoff'
    assert isinstance(result['created_at'], datetime)

    mock_retrieve_sub.assert_not_awaited()

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

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'unknown' # Default value
    assert result['recurring'] is False
    assert result['amount'] == Decimal('0.00') # Default value, not from input for unknown
    assert result['customer_id'] == 'cus_unknown'
    assert result['customer_email'] == 'unknown@example.com'
    assert result['subscription_id'] is None
    assert result['plan_id'] is None
    assert result['product_id'] is None
    assert result['transaction_id'] == 'unknown_123'
    assert isinstance(result['created_at'], datetime)

@pytest.mark.asyncio
async def test_analyze_transaction_exception(stripe_service, mocker):
    """Test analyze_transaction when an internal exception occurs."""
    transaction_data = {
        "id": "pi_analyze_err",
        "object_type": "payment_intent",
        "amount": Decimal('15.99'),
        "customer_id": "cus_analyze_err",
        "customer_email": "analyze_err@example.com",
        "created_at": datetime.now(timezone.utc)
    }

    # Mock the retrieve call to raise an exception
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock, side_effect=Exception('API Error during analysis'))

    with pytest.raises(Exception, match='API Error during analysis'):
        await stripe_service.analyze_transaction(transaction_data)

    mock_retrieve_pi.assert_awaited_once_with("pi_analyze_err", expand=["metadata"])

# --- Tests for handle_subscription_renewal ---

@pytest.mark.asyncio
async def test_handle_subscription_renewal_success(stripe_service, mocker):
    """Test handling a subscription renewal successfully."""
    subscription_id = 'sub_renew_ok'
    mock_subscription = MagicMock(id=subscription_id)

    # Mock Stripe API call
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock, return_value=mock_subscription)

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is True
    mock_retrieve_sub.assert_awaited_once_with(subscription_id)
    # In a real scenario, we'd also check if credits were added or DB updated

@pytest.mark.asyncio
async def test_handle_subscription_renewal_not_found(stripe_service, mocker):
    """Test handling renewal when the subscription is not found."""
    subscription_id = 'sub_renew_404'

    # Mock Stripe API call to return None (or raise specific not found error)
    # stripe.Subscription.retrieve raises InvalidRequestError for not found
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such subscription', 'id'))

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is False
    mock_retrieve_sub.assert_awaited_once_with(subscription_id)

@pytest.mark.asyncio
async def test_handle_subscription_renewal_exception(stripe_service, mocker):
    """Test handling renewal when an exception occurs during retrieval."""
    subscription_id = 'sub_renew_err'

@pytest.mark.asyncio
async def test_cancel_subscription_success(stripe_service, mocker):
    """Test cancelling a subscription successfully."""
    subscription_id = 'sub_cancel_ok'
    mock_result = MagicMock(cancel_at_period_end=True)

    # Mock Stripe API call
    mock_modify_sub = mocker.patch('stripe.Subscription.modify', new_callable=AsyncMock, return_value=mock_result)

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is True
    mock_modify_sub.assert_awaited_once_with(subscription_id, cancel_at_period_end=True)

@pytest.mark.asyncio
async def test_cancel_subscription_failure(stripe_service, mocker):
    """Test cancelling a subscription when Stripe doesn't confirm cancellation."""
    subscription_id = 'sub_cancel_fail'
    # Simulate Stripe returning something unexpected or False for cancel_at_period_end
    mock_result = MagicMock(cancel_at_period_end=False)

    # Mock Stripe API call
    mock_modify_sub = mocker.patch('stripe.Subscription.modify', new_callable=AsyncMock, return_value=mock_result)

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False
    mock_modify_sub.assert_awaited_once_with(subscription_id, cancel_at_period_end=True)

@pytest.mark.asyncio
async def test_cancel_subscription_not_found(stripe_service, mocker):
    """Test cancelling a subscription that is not found."""
    subscription_id = 'sub_cancel_404'

    # Mock Stripe API call to raise InvalidRequestError
    mock_modify_sub = mocker.patch('stripe.Subscription.modify', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such subscription', 'id'))

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False
    mock_modify_sub.assert_awaited_once_with(subscription_id, cancel_at_period_end=True)

@pytest.mark.asyncio
async def test_cancel_subscription_exception(stripe_service, mocker):
    """Test cancelling a subscription when a general exception occurs."""
    subscription_id = 'sub_cancel_err'

    # Mock Stripe API call to raise a generic exception
    mock_modify_sub = mocker.patch('stripe.Subscription.modify', new_callable=AsyncMock, side_effect=Exception('API Error'))

    result = await stripe_service.cancel_subscription(subscription_id)

    assert result is False
    mock_modify_sub.assert_awaited_once_with(subscription_id, cancel_at_period_end=True)


    # Mock Stripe API call to raise a generic exception
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock, side_effect=Exception('API Error'))

    result = await stripe_service.handle_subscription_renewal(subscription_id)

    assert result is False
    mock_retrieve_sub.assert_awaited_once_with(subscription_id)

# --- Tests for cancel_subscription ---

    result = await stripe_service.analyze_transaction(transaction_data)

    assert result['transaction_type'] == 'unknown' # Default value
    assert result['recurring'] is False
    assert result['amount'] == Decimal('0.00') # Default value, not from input for unknown
    assert result['customer_id'] == 'cus_unknown'
    assert result['customer_email'] == 'unknown@example.com'
    assert result['subscription_id'] is None
    assert result['plan_id'] is None
    assert result['product_id'] is None
    assert result['transaction_id'] == 'unknown_123'
    assert isinstance(result['created_at'], datetime)

@pytest.mark.asyncio
async def test_analyze_transaction_exception(stripe_service, mocker):
    """Test analyze_transaction when an internal exception occurs."""
    transaction_data = {
        "id": "pi_analyze_err",
        "object_type": "payment_intent",
        "amount": Decimal('15.99'),
        "customer_id": "cus_analyze_err",
        "customer_email": "analyze_err@example.com",
        "created_at": datetime.now(timezone.utc)
    }

    # Mock the retrieve call to raise an exception
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock, side_effect=Exception('API Error during analysis'))

    with pytest.raises(Exception, match='API Error during analysis'):
        await stripe_service.analyze_transaction(transaction_data)

    mock_retrieve_pi.assert_awaited_once_with("pi_analyze_err", expand=["metadata"])

# --- Tests for handle_subscription_renewal --- 

    mock_list_sub.assert_awaited_once_with(customer=customer_id, limit=10)

@pytest.mark.asyncio
async def test_find_transactions_by_email_exception(stripe_service, mocker):
    """Test finding transactions by email when an exception occurs."""
    test_email = 'error@example.com'

    # Mock Stripe API call to raise an exception
    mock_list_cus = mocker.patch('stripe.Customer.list', new_callable=AsyncMock, side_effect=Exception('API Error'))
    mock_list_pi = mocker.patch('stripe.PaymentIntent.list', new_callable=AsyncMock)
    mock_list_sub = mocker.patch('stripe.Subscription.list', new_callable=AsyncMock)

    results = await stripe_service.find_transactions_by_email(test_email)

    assert len(results) == 0
    mock_list_cus.assert_awaited_once_with(email=test_email, limit=5)
    mock_list_pi.assert_not_awaited()
    mock_list_sub.assert_not_awaited()

# --- Tests for _format_transaction --- 

    mock_retrieve_inv.assert_awaited_once_with(transaction_id)
    mock_retrieve_ch.assert_awaited_once_with(transaction_id)

@pytest.mark.asyncio
async def test_find_transaction_by_id_general_exception(stripe_service, mocker):
    """Test finding a transaction by ID when a general exception occurs."""
    # Mock the first retrieve to raise a generic Exception
    mock_retrieve_pi = mocker.patch('stripe.PaymentIntent.retrieve', new_callable=AsyncMock, side_effect=Exception('Something went wrong'))
    # Mock others just in case, though they shouldn't be called
    mock_retrieve_sub = mocker.patch('stripe.Subscription.retrieve', new_callable=AsyncMock)
    mock_retrieve_inv = mocker.patch('stripe.Invoice.retrieve', new_callable=AsyncMock)
    mock_retrieve_ch = mocker.patch('stripe.Charge.retrieve', new_callable=AsyncMock)

    transaction_id = 'error_id'
    result = await stripe_service.find_transaction_by_id(transaction_id)

    assert result is None
    mock_retrieve_pi.assert_awaited_once_with(transaction_id)
    mock_retrieve_sub.assert_not_awaited()
    mock_retrieve_inv.assert_not_awaited()
    mock_retrieve_ch.assert_not_awaited()

# --- Tests for find_transactions_by_email --- 

    assert isinstance(result['created_at'], datetime)
    assert 'subscription_data' in result
    assert result['subscription_data']['status'] == 'active'
    assert result['subscription_data']['items'] == [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]

    mock_retrieve_pi.assert_awaited_once_with(transaction_id)
    mock_retrieve_sub.assert_awaited_once_with(transaction_id)
    mock_retrieve_cus.assert_awaited_once_with('cus_def')
    mock_retrieve_inv.assert_not_awaited()
    mock_retrieve_ch.assert_not_awaited()
