import pytest
from unittest.mock import patch, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import asyncio

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

# Assuming conftest.py in the same directory will provide these:
# from .conftest import stripe_service, create_stripe_mock

pytestmark = pytest.mark.asyncio

# --- Tests for analyze_transaction ---

# async def test_analyze_transaction_payment_intent(stripe_service, mocker):
#     """Test analyzing a PaymentIntent transaction."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#     billing_details_mock = stripe_service.create_stripe_mock(email='test@example.com')
#     charge_mock = stripe_service.create_stripe_mock(billing_details=billing_details_mock)
#     charges_mock = stripe_service.create_stripe_mock(data=[charge_mock])
#
#     mock_pi = stripe_service.create_stripe_mock(
#         id='pi_analyze_1', object='payment_intent', amount=7500,
#         customer='cus_analyze', created=timestamp, charges=charges_mock
#     )
#
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_analyze(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             return mock_pi
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_analyze
#
#     # Assuming analyze_transaction is a method of stripe_service
#     analyzed_data = await stripe_service.analyze_transaction('pi_analyze_1')
#
#     assert analyzed_data is not None
#     assert analyzed_data['id'] == 'pi_analyze_1'
#     assert analyzed_data['object_type'] == 'payment_intent'
#     assert analyzed_data['amount'] == Decimal('75.00')
#     assert analyzed_data['customer_id'] == 'cus_analyze'
#     assert analyzed_data['customer_email'] == 'test@example.com'
#     assert isinstance(analyzed_data['created_at'], datetime)
#     mock_to_thread.assert_called_once_with(stripe.PaymentIntent.retrieve, 'pi_analyze_1')


# async def test_analyze_transaction_subscription(stripe_service, mocker):
#     """Test analyzing a Subscription transaction."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#     items_data = [{'id': 'si_analyze', 'plan': {'id': 'plan_analyze'}}]
#     items_mock = stripe_service.create_stripe_mock(data=items_data)
#
#     mock_sub = stripe_service.create_stripe_mock(
#         id='sub_analyze_1', object='subscription', customer='cus_sub_analyze',
#         created=timestamp, status='trialing', current_period_start=timestamp - 2000,
#         current_period_end=timestamp + 2000, items=items_mock
#     )
#     mock_customer = stripe_service.create_stripe_mock(id='cus_sub_analyze', email='sub_customer@example.com')
#
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_analyze(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve: # First try
#             raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
#         elif func == stripe.Subscription.retrieve: # Second try
#             return mock_sub
#         elif func == stripe.Customer.retrieve: # Called for subscription
#             assert args[0] == 'cus_sub_analyze'
#             return mock_customer
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_analyze
#
#     analyzed_data = await stripe_service.analyze_transaction('sub_analyze_1')
#
#     assert analyzed_data is not None
#     assert analyzed_data['id'] == 'sub_analyze_1'
#     assert analyzed_data['object_type'] == 'subscription'
#     assert analyzed_data['customer_id'] == 'cus_sub_analyze'
#     assert analyzed_data['customer_email'] == 'sub_customer@example.com'
#     assert analyzed_data['subscription_data']['status'] == 'trialing'
#     assert analyzed_data['subscription_data']['items'] == [{'id': 'si_analyze', 'plan': {'id': 'plan_analyze'}}]
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, 'sub_analyze_1') for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, 'sub_analyze_1') for call in calls)
#     assert any(call == mocker.call(stripe.Customer.retrieve, 'cus_sub_analyze') for call in calls)


# async def test_analyze_transaction_invoice_for_subscription(stripe_service, mocker):
#     """Test analyzing an Invoice transaction linked to a subscription."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#     mock_invoice = stripe_service.create_stripe_mock(
#         id='in_analyze_sub', object='invoice', amount_paid=1500,
#         customer='cus_inv_sub', customer_email='inv_sub@example.com',
#         subscription='sub_linked_analyze', created=timestamp
#     )
#
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_analyze(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             raise stripe.error.InvalidRequestError('No such payment_intent', 'id')
#         elif func == stripe.Subscription.retrieve:
#             raise stripe.error.InvalidRequestError('No such subscription', 'id')
#         elif func == stripe.Invoice.retrieve:
#             return mock_invoice
#         else:
#             raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
#
#     mock_to_thread.side_effect = side_effect_analyze
#
#     analyzed_data = await stripe_service.analyze_transaction('in_analyze_sub')
#
#     assert analyzed_data is not None
#     assert analyzed_data['id'] == 'in_analyze_sub'
#     assert analyzed_data['object_type'] == 'invoice'
#     assert analyzed_data['amount'] == Decimal('15.00')
#     assert analyzed_data['customer_id'] == 'cus_inv_sub'
#     assert analyzed_data['customer_email'] == 'inv_sub@example.com'
#     assert analyzed_data['subscription_id'] == 'sub_linked_analyze'
#
#     calls = mock_to_thread.call_args_list
#     assert any(call == mocker.call(stripe.PaymentIntent.retrieve, 'in_analyze_sub') for call in calls)
#     assert any(call == mocker.call(stripe.Subscription.retrieve, 'in_analyze_sub') for call in calls)
#     assert any(call == mocker.call(stripe.Invoice.retrieve, 'in_analyze_sub') for call in calls)


# async def test_analyze_transaction_invoice_one_off(stripe_service, mocker):
#     """Test analyzing an Invoice transaction not linked to a subscription (one-off)."""
#     timestamp = int(datetime.now(timezone.utc).timestamp())
#     mock_invoice = stripe_service.create_stripe_mock(
#         id='in_analyze_oneoff', object='invoice', amount_paid=2000,
#         customer='cus_inv_oneoff', customer_email='inv_oneoff@example.com',
#         subscription=None, # Key difference
#         created=timestamp
#     )
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock, side_effect=[
#         stripe.error.InvalidRequestError('No such payment_intent', 'id'), # PI fails
#         stripe.error.InvalidRequestError('No such subscription', 'id'), # Sub fails
#         mock_invoice # Invoice succeeds
#     ])
#
#     analyzed_data = await stripe_service.analyze_transaction('in_analyze_oneoff')
#
#     assert analyzed_data is not None
#     assert analyzed_data['id'] == 'in_analyze_oneoff'
#     assert analyzed_data['object_type'] == 'invoice'
#     assert analyzed_data['amount'] == Decimal('20.00')
#     assert analyzed_data['subscription_id'] is None


# async def test_analyze_transaction_unknown_type(stripe_service, mocker):
#     """Test analyzing a transaction of an unknown type (should return None)."""
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock, side_effect=stripe.error.InvalidRequestError('No such object', 'id'))
#
#     analyzed_data = await stripe_service.analyze_transaction('unknown_id_123')
#     assert analyzed_data is None
#     assert mock_to_thread.call_count == 4 # Tried all 4 types


# async def test_analyze_transaction_exception(stripe_service, mocker):
#     """Test analyze_transaction when an internal exception occurs during API call."""
#     mock_to_thread = mocker.patch('asyncio.to_thread', new_callable=AsyncMock)
#
#     async def side_effect_analyze_err(func, *args, **kwargs):
#         if func == stripe.PaymentIntent.retrieve:
#             raise Exception("Simulated internal error")
#         raise stripe.error.InvalidRequestError(f'No such {func.__name__.lower()}', 'id')
#
#     mock_to_thread.side_effect = side_effect_analyze_err
#
#     analyzed_data = await stripe_service.analyze_transaction('err_id_analyze')
#     assert analyzed_data is None
#     mock_to_thread.assert_any_call(stripe.PaymentIntent.retrieve, 'err_id_analyze')