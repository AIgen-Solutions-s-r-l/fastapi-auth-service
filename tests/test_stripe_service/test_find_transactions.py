import pytest
from unittest.mock import patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import asyncio

import stripe
from sqlalchemy.ext.asyncio import AsyncSession # Keep this for type hints if used in this file

# Assuming conftest.py in the same directory will provide these:
# from .conftest import stripe_service, create_stripe_mock

# If models are directly used for assertions, import them:
# from app.models.user import User as UserModel
# from app.models.plan import Subscription as SubscriptionModel
# from app.core.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio

# --- Tests for find_transaction_by_id ---

# @pytest.mark.asyncio # Already marked by pytestmark
# async def test_find_transaction_by_id_payment_intent_success(stripe_service, mocker):
#     """Test finding a transaction by ID when it's a PaymentIntent."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#
#     # Using create_stripe_mock from conftest
#     billing_details_mock = stripe_service.create_stripe_mock(email='test@example.com')
#     charge_mock = stripe_service.create_stripe_mock(billing_details=billing_details_mock)
#     charges_mock = stripe_service.create_stripe_mock(data=[charge_mock])
#
#     mock_payment_intent = stripe_service.create_stripe_mock(
#         id='pi_123',
#         object='payment_intent',
#         amount=5000,
#         customer='cus_abc',
#         created=timestamp,
#         charges=charges_mock
#     )
#
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             return mock_payment_intent
#         elif func in [stripe.Subscription.retrieve, stripe.Invoice.retrieve, stripe.Charge.retrieve]:
#              raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#
#     transaction_id = 'pi_123'
#     # Assuming find_transaction_by_id is a method of stripe_service
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#
#     assert result is not None
#     assert result['id'] == transaction_id
#     assert result['object_type'] == 'payment_intent'
#     assert result['amount'] == Decimal('50.00')
#     assert result['customer_id'] == 'cus_abc'
#     assert result['customer_email'] == 'test@example.com'
#     assert isinstance(result['created_at'], datetime)
#
#     mock_to_thread.assert_any_call(stripe.PaymentIntent.retrieve, transaction_id)
#     assert not any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in mock_to_thread.call_args_list)


# async def test_find_transaction_by_id_subscription_success(stripe_service, mocker):
#     """Test finding a transaction by ID when it's a Subscription."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#
#     items_data = [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]
#     items_mock = stripe_service.create_stripe_mock(data=items_data)
#
#     mock_subscription = stripe_service.create_stripe_mock(
#         id='sub_456',
#         object='subscription',
#         customer='cus_def',
#         created=timestamp,
#         status='active',
#         current_period_start=timestamp - 10000,
#         current_period_end=timestamp + 10000,
#         items=items_mock
#     )
#     mock_customer = stripe_service.create_stripe_mock(
#         id='cus_def',
#         email='customer@example.com'
#     )
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
#         elif func == stripe.Subscription.retrieve:
#             return mock_subscription
#         elif func == stripe.Customer.retrieve:
#              assert args[0] == 'cus_def'
#              return mock_customer
#         elif func in [stripe.Invoice.retrieve, stripe.Charge.retrieve]:
#              raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     transaction_id = 'sub_456'
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#
#     assert result is not None
#     assert result['id'] == transaction_id
#     assert result['object_type'] == 'subscription'
#     assert result['customer_id'] == 'cus_def'
#     assert result['customer_email'] == 'customer@example.com'
#     assert isinstance(result['created_at'], datetime)
#     assert 'subscription_data' in result
#     assert result['subscription_data']['status'] == 'active'
#     assert result['subscription_data']['items'] == [{'id': 'si_1', 'plan': {'id': 'plan_1'}}]
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Customer.retrieve, 'cus_def') for call in calls)
#     assert not any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)


# async def test_find_transaction_by_id_invoice_success(stripe_service, mocker):
#     """Test finding a transaction by ID when it's an Invoice."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#
#     mock_invoice = stripe_service.create_stripe_mock(
#         id='in_789',
#         object='invoice',
#         amount_paid=2500,
#         customer='cus_ghi',
#         customer_email='invoice@example.com',
#         subscription='sub_xyz',
#         created=timestamp
#     )
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
#         elif func == stripe.Subscription.retrieve:
#             raise stripe.error.InvalidRequestError('No such subscription', 'id')
#         elif func == stripe.Invoice.retrieve:
#             return mock_invoice
#         elif func == stripe.Charge.retrieve:
#              raise stripe.error.InvalidRequestError(f'Simulated error for {func.__name__}', 'id')
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     transaction_id = 'in_789'
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#
#     assert result is not None
#     assert result['id'] == transaction_id
#     assert result['object_type'] == 'invoice'
#     assert result['amount'] == Decimal('25.00')
#     assert result['customer_id'] == 'cus_ghi'
#     assert result['customer_email'] == 'invoice@example.com'
#     assert result['subscription_id'] == 'sub_xyz'
#     assert isinstance(result['created_at'], datetime)
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
#     assert not any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


# async def test_find_transaction_by_id_charge_success(stripe_service, mocker):
#     """Test finding a transaction by ID when it's a Charge."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#
#     billing_details_mock = stripe_service.create_stripe_mock(email='charge@example.com')
#     mock_charge = stripe_service.create_stripe_mock(
#         id='ch_abc',
#         object='charge',
#         amount=1000,
#         customer='cus_jkl',
#         created=timestamp,
#         billing_details=billing_details_mock
#     )
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
#         elif func == stripe.Subscription.retrieve:
#             raise stripe.error.InvalidRequestError('No such subscription', 'id')
#         elif func == stripe.Invoice.retrieve:
#             raise stripe.error.InvalidRequestError('No such invoice', 'id')
#         elif func == stripe.Charge.retrieve:
#             return mock_charge
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     transaction_id = 'ch_abc'
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#
#     assert result is not None
#     assert result['id'] == transaction_id
#     assert result['object_type'] == 'charge'
#     assert result['amount'] == Decimal('10.00')
#     assert result['customer_id'] == 'cus_jkl'
#     assert result['customer_email'] == 'charge@example.com'
#     assert isinstance(result['created_at'], datetime)
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


# async def test_find_transaction_by_id_not_found(stripe_service, mocker):
#     """Test finding a transaction by ID when it doesn't exist."""
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func in [stripe.PaymentIntent.retrieve, stripe.Subscription.retrieve, stripe.Invoice.retrieve, stripe.Charge.retrieve]:
#             raise stripe.error.InvalidRequestError(f'No such {func.__name__.lower()}', 'id')
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     transaction_id = 'non_existent_id'
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#
#     assert result is None
#
#     calls = mock_to_thread.call_args_list
#     assert mock_to_thread.call_count == 4
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


# async def test_find_transaction_by_id_general_exception(stripe_service, mocker):
#     """Test finding a transaction by ID when general exceptions occur during lookups."""
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func in [stripe.PaymentIntent.retrieve, stripe.Subscription.retrieve,
#                    stripe.Invoice.retrieve, stripe.Charge.retrieve]:
#             raise Exception(f'Error in {func.__name__}')
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     transaction_id = 'error_id'
#     result = await stripe_service.find_transaction_by_id(transaction_id)
#     assert result is None
#
#     calls = mock_to_thread.await_args_list # Note: pytest-mock uses await_args_list for AsyncMock
#     assert len(calls) == 4
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Invoice.retrieve, transaction_id) for call in calls)
#     assert any(call == mocker.call(stripe.Charge.retrieve, transaction_id) for call in calls)


# --- Tests for find_transactions_by_email ---

# async def test_find_transactions_by_email_success(stripe_service, mocker):
#     """Test finding transactions by email successfully."""
#     test_email = 'found@example.com'
#     customer_id = 'cus_found'
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#
#     mock_customer = stripe_service.create_stripe_mock(id=customer_id)
#     mock_customer_list_obj = stripe_service.create_stripe_mock(data=[mock_customer])
#     billing_details_mock = stripe_service.create_stripe_mock(email=test_email)
#     charge_mock = stripe_service.create_stripe_mock(billing_details=billing_details_mock)
#     charges_mock = stripe_service.create_stripe_mock(data=[charge_mock])
#
#     mock_pi = stripe_service.create_stripe_mock(
#         id='pi_email_1', object='payment_intent', amount=3000,
#         customer=customer_id, created=timestamp - 5000, charges=charges_mock
#     )
#     mock_pi_list_obj = stripe_service.create_stripe_mock(data=[mock_pi])
#     items_data = [{'id': 'si_email', 'plan': {'id': 'plan_email'}}]
#     items_mock = stripe_service.create_stripe_mock(data=items_data)
#
#     mock_sub = stripe_service.create_stripe_mock(
#         id='sub_email_1', object='subscription', customer=customer_id, created=timestamp,
#         status='active', current_period_start=timestamp - 10000,
#         current_period_end=timestamp + 10000, items=items_mock
#     )
#     mock_sub_list_obj = stripe_service.create_stripe_mock(data=[mock_sub])
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.Customer.list:
#             assert kwargs.get('email') == test_email
#             return mock_customer_list_obj
#         elif func == stripe.PaymentIntent.list:
#             assert kwargs.get('customer') == customer_id
#             return mock_pi_list_obj
#         elif func == stripe.Subscription.list:
#             assert kwargs.get('customer') == customer_id
#             return mock_sub_list_obj
#         else:
#              raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     results = await stripe_service.find_transactions_by_email(test_email)
#
#     assert len(results) == 2
#     assert results[0]['id'] == 'sub_email_1'
#     assert results[0]['object_type'] == 'subscription'
#     assert results[0]['customer_email'] == test_email
#     assert results[1]['id'] == 'pi_email_1'
#     assert results[1]['object_type'] == 'payment_intent'
#     assert results[1]['amount'] == Decimal('30.00')
#     assert results[1]['customer_email'] == test_email
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.Customer.list, email=test_email, limit=5) for call in calls)
#     assert any(call == mocker.call(stripe.PaymentIntent.list, customer=customer_id, limit=10) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.list, customer=customer_id, limit=10) for call in calls)


# async def test_find_transactions_by_email_no_customer(stripe_service, mocker):
#     """Test finding transactions when no customer matches the email."""
#     test_email = 'notfound@example.com'
#     mock_customer_list_obj = stripe_service.create_stripe_mock(data=[]) # Use create_stripe_mock
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.Customer.list:
#             assert kwargs.get('email') == test_email
#             return mock_customer_list_obj
#         elif func in [stripe.PaymentIntent.list, stripe.Subscription.list]:
#              raise AssertionError(f"Should not call {func.__name__} if no customer found")
#         else:
#              raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     results = await stripe_service.find_transactions_by_email(test_email)
#
#     assert len(results) == 0
#     mock_to_thread.assert_called_once_with(stripe.Customer.list, email=test_email, limit=5)


# async def test_find_transactions_by_email_customer_no_transactions(stripe_service, mocker):
#     """Test finding transactions when customer exists but has no transactions."""
#     test_email = 'customer_no_trans@example.com'
#     customer_id = 'cus_no_trans'
#
#     mock_customer = stripe_service.create_stripe_mock(id=customer_id)
#     mock_customer_list_obj = stripe_service.create_stripe_mock(data=[mock_customer])
#     mock_pi_list_obj = stripe_service.create_stripe_mock(data=[])
#     mock_sub_list_obj = stripe_service.create_stripe_mock(data=[])
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.Customer.list:
#             return mock_customer_list_obj
#         elif func == stripe.PaymentIntent.list:
#             return mock_pi_list_obj
#         elif func == stripe.Subscription.list:
#             return mock_sub_list_obj
#         else:
#              raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     results = await stripe_service.find_transactions_by_email(test_email)
#
#     assert len(results) == 0
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.Customer.list, email=test_email, limit=5) for call in calls)
#     assert any(call == mocker.call(stripe.PaymentIntent.list, customer=customer_id, limit=10) for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.list, customer=customer_id, limit=10) for call in calls)


# async def test_find_transactions_by_email_exception(stripe_service, mocker):
#     """Test finding transactions by email when an exception occurs during customer lookup."""
#     test_email = 'exception@example.com'
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_to_thread(func, *args, **kwargs):
#         if func == stripe.Customer.list:
#             raise stripe.error.StripeError("Simulated API error")
#         else:
#              raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_to_thread
#     results = await stripe_service.find_transactions_by_email(test_email)
#     assert len(results) == 0
#     mock_to_thread.assert_called_once_with(stripe.Customer.list, email=test_email, limit=5)