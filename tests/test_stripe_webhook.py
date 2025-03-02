"""Tests for Stripe webhook handling."""

import json
import pytest
import hmac
import hashlib
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException, Request, BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app


# Fixtures and mocks
@pytest.fixture
def mock_stripe_webhook_secret():
    """Return a mock Stripe webhook secret."""
    return "whsec_REMOVED_secret"


@pytest.fixture
def mock_stripe_invoice_payment_succeeded_event():
    """Return a mock Stripe invoice.payment_succeeded event."""
    return {
        "id": "evt_1234567890",
        "object": "event",
        "api_version": "2023-10-16",
        "created": int(datetime.now(UTC).timestamp()),
        "data": {
            "object": {
                "id": "in_1234567890",
                "object": "invoice",
                "amount_paid": 4999,  # $49.99
                "currency": "usd",
                "customer": "cus_1234567890",
                "customer_email": "customer@example.com",
                "subscription": "sub_1234567890",
                "status": "paid",
                "lines": {
                    "data": [
                        {
                            "id": "il_1234567890",
                            "object": "line_item",
                            "amount": 4999,
                            "currency": "usd",
                            "plan": {
                                "id": "price_1234567890",
                                "product": "prod_1234567890"
                            }
                        }
                    ]
                }
            }
        },
        "type": "invoice.payment_succeeded"
    }


@pytest.fixture
def mock_stripe_customer_subscription_updated_event():
    """Return a mock Stripe customer.subscription.updated event."""
    return {
        "id": "evt_2345678901",
        "object": "event",
        "api_version": "2023-10-16",
        "created": int(datetime.now(UTC).timestamp()),
        "data": {
            "object": {
                "id": "sub_1234567890",
                "object": "subscription",
                "customer": "cus_1234567890",
                "status": "active",
                "current_period_start": int(datetime.now(UTC).timestamp()),
                "current_period_end": int(datetime.now(UTC).timestamp()) + 2592000,  # +30 days
                "items": {
                    "data": [
                        {
                            "id": "si_1234567890",
                            "plan": {
                                "id": "price_1234567890",
                                "product": "prod_1234567890",
                                "amount": 4999,
                                "currency": "usd"
                            }
                        }
                    ]
                }
            },
            "previous_attributes": {
                "status": "incomplete"
            }
        },
        "type": "customer.subscription.updated"
    }


@pytest.fixture
def mock_stripe_payment_intent_succeeded_event():
    """Return a mock Stripe payment_intent.succeeded event."""
    return {
        "id": "evt_3456789012",
        "object": "event",
        "api_version": "2023-10-16",
        "created": int(datetime.now(UTC).timestamp()),
        "data": {
            "object": {
                "id": "pi_1234567890",
                "object": "payment_intent",
                "amount": 2999,  # $29.99
                "currency": "usd",
                "customer": "cus_1234567890",
                "metadata": {
                    "product_id": "prod_oneoff_credits"
                },
                "charges": {
                    "data": [
                        {
                            "id": "ch_1234567890",
                            "billing_details": {
                                "email": "customer@example.com"
                            }
                        }
                    ]
                }
            }
        },
        "type": "payment_intent.succeeded"
    }


@pytest.fixture
def mock_credit_service():
    """Mock credit service for webhook tests."""
    mock = AsyncMock()
    
    # Mock renew_subscription method
    mock.renew_subscription.return_value = (
        MagicMock(id=123, new_balance=Decimal('500.00')),
        MagicMock(id=456)
    )
    
    # Mock purchase_one_time_credits method
    mock.purchase_one_time_credits.return_value = MagicMock(
        id=789, 
        new_balance=Decimal('300.00')
    )
    
    # Mock get_subscription_by_stripe_id method
    mock.get_subscription_by_stripe_id.return_value = MagicMock(
        id=456, user_id=1, plan_id=100, is_active=True, auto_renew=True
    )
    
    # Mock get_user_by_stripe_customer_id method
    mock.get_user_by_stripe_customer_id.return_value = MagicMock(
        id=1, 
        email="customer@example.com", 
        username="testuser"
    )
    
    return mock


def generate_stripe_signature(payload, secret, timestamp=None):
    """
    Generate a Stripe signature for testing webhook verification.
    
    Args:
        payload: The JSON payload as a string
        secret: The webhook secret key
        timestamp: Optional timestamp (defaults to current time)
        
    Returns:
        A valid Stripe signature string
    """
    if timestamp is None:
        timestamp = int(datetime.now(UTC).timestamp())
    
    # Create the signed_payload string
    signed_payload = f"{timestamp}.{payload}"
    
    # Create the signature using HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Format the signature as Stripe expects
    return f"t={timestamp},v1={signature}"


class TestStripeWebhook:
    """Tests for Stripe webhook handling."""
    
    @pytest.mark.asyncio
    @patch('app.routers.stripe_webhook.StripeService')  # Add StripeService mock
    @patch('app.routers.stripe_webhook.CreditService')
    @patch('stripe.Webhook.construct_event')
    async def test_handle_invoice_payment_succeeded(
        self,
        mock_construct_event,
        mock_credit_service_class,
        mock_stripe_service_class,  # Add new parameter
        mock_credit_service,
        mock_stripe_invoice_payment_succeeded_event
    ):
        """Test handling an invoice.payment_succeeded webhook event."""
        # This would be imported from the webhook router in your actual implementation
        from app.routers.stripe_webhook import stripe_webhook_handler
        
        # Set up mock services
        mock_credit_service_class.return_value = mock_credit_service
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up mock event construction
        mock_construct_event.return_value = mock_stripe_invoice_payment_succeeded_event
        
        # Create mock request with signature
        payload = json.dumps(mock_stripe_invoice_payment_succeeded_event)
        stripe_signature = generate_stripe_signature(payload, "whsec_REMOVED_secret")
        
        # Create mock request object
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"Stripe-Signature": stripe_signature}
        mock_request.body.return_value = payload.encode('utf-8')
        
        # Create mock background tasks
        mock_background_tasks = MagicMock(spec=BackgroundTasks)
        
        # Create mock database
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Call the webhook handler
        response = await stripe_webhook_handler(
            request=mock_request,
            background_tasks=mock_background_tasks,
            db=mock_db
        )
        
        # Assert
        assert response["status"] == "success"
        assert response["event_type"] == "invoice.payment_succeeded"
        assert response["processed"] is True
        
        # Assert subscription renewal was called
        mock_credit_service.get_subscription_by_stripe_id.assert_called_once_with("sub_1234567890")
        mock_credit_service.renew_subscription.assert_called_once_with(
            subscription_id=456,
            background_tasks=mock_background_tasks
        )
    
    @pytest.mark.asyncio
    @patch('app.routers.stripe_webhook.CreditService')
    @patch('app.routers.stripe_webhook.StripeService')
    @patch('stripe.Webhook.construct_event')
    async def test_handle_customer_subscription_updated(
        self,
        mock_construct_event,
        mock_stripe_service_class,
        mock_credit_service_class,
        mock_credit_service,
        mock_stripe_customer_subscription_updated_event
    ):
        """Test handling a customer.subscription.updated webhook event."""
        # This would be imported from the webhook router in your actual implementation
        from app.routers.stripe_webhook import stripe_webhook_handler
        
        # Set up mock services
        mock_credit_service_class.return_value = mock_credit_service
        # Set up user that will be returned
        mock_user = MagicMock(id=1, email="customer@example.com", username="testuser")
        mock_credit_service.get_user_by_stripe_customer_id.return_value = mock_user
        
        # Set up stripe service
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up mock event construction
        mock_construct_event.return_value = mock_stripe_customer_subscription_updated_event
        
        # Create mock request with signature
        payload = json.dumps(mock_stripe_customer_subscription_updated_event)
        stripe_signature = generate_stripe_signature(payload, "whsec_REMOVED_secret")
        
        # Create mock request object
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"Stripe-Signature": stripe_signature}
        mock_request.body.return_value = payload.encode('utf-8')
        
        # Create mock background tasks
        mock_background_tasks = MagicMock(spec=BackgroundTasks)
        
        # Create mock database
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Call the webhook handler
        response = await stripe_webhook_handler(
            request=mock_request,
            background_tasks=mock_background_tasks,
            db=mock_db
        )
        
        # Assert
        assert response["status"] == "success"
        assert response["event_type"] == "customer.subscription.updated"
        assert response["processed"] is True
        
        # Assert subscription update was processed
        mock_credit_service.get_user_by_stripe_customer_id.assert_called_once_with("cus_1234567890")
        mock_credit_service.update_subscription_status.assert_called_once_with(
            stripe_subscription_id="sub_1234567890",
            status="active"
        )
    
    @pytest.mark.asyncio
    @patch('app.routers.stripe_webhook.CreditService')
    @patch('app.routers.stripe_webhook.StripeService')
    @patch('stripe.Webhook.construct_event')
    async def test_handle_payment_intent_succeeded(
        self,
        mock_construct_event,
        mock_stripe_service_class,
        mock_credit_service_class,
        mock_credit_service,
        mock_stripe_payment_intent_succeeded_event
    ):
        """Test handling a payment_intent.succeeded webhook event."""
        # This would be imported from the webhook router in your actual implementation
        from app.routers.stripe_webhook import stripe_webhook_handler
        
        # Set up mock services
        mock_credit_service_class.return_value = mock_credit_service
        
        # Set up user that will be returned
        mock_user = MagicMock(id=1, email="customer@example.com", username="testuser")
        mock_credit_service.get_user_by_stripe_customer_id.return_value = mock_user
        
        # Set up active plans for credit calculation
        mock_plan = MagicMock(id=1, price=Decimal('29.99'), credit_amount=Decimal('300.00'))
        mock_credit_service.get_all_active_plans.return_value = [mock_plan]
        
        # Set up transaction to be returned by purchase_one_time_credits
        mock_transaction = MagicMock(id=789, amount=Decimal('300.00'), new_balance=Decimal('300.00'))
        mock_credit_service.purchase_one_time_credits.return_value = mock_transaction
        
        # Set up stripe service
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up analysis result for the payment intent - with _format_transaction call
        mock_stripe_service._format_transaction.return_value = {
            "transaction_id": "pi_1234567890",
            "customer_id": "cus_1234567890",
            "amount": 2999,
        }
        
        # Analysis result that will be returned by analyze_transaction
        analysis_result = {
            "transaction_type": "oneoff",
            "recurring": False,
            "amount": Decimal('29.99'),
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "subscription_id": None,
            "plan_id": None,
            "product_id": "prod_oneoff_credits",
            "transaction_id": "pi_1234567890",
            "created_at": datetime.now(UTC),
        }
        mock_stripe_service.analyze_transaction.return_value = analysis_result
        
        # Set up mock event construction
        mock_construct_event.return_value = mock_stripe_payment_intent_succeeded_event
        
        # Create mock request with signature
        payload = json.dumps(mock_stripe_payment_intent_succeeded_event)
        stripe_signature = generate_stripe_signature(payload, "whsec_REMOVED_secret")
        
        # Create mock request object
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"Stripe-Signature": stripe_signature}
        mock_request.body.return_value = payload.encode('utf-8')
        
        # Create mock background tasks
        mock_background_tasks = MagicMock(spec=BackgroundTasks)
        
        # Create mock database
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Call the webhook handler
        response = await stripe_webhook_handler(
            request=mock_request,
            background_tasks=mock_background_tasks,
            db=mock_db
        )
        
        # Assert
        assert response["status"] == "success"
        assert response["event_type"] == "payment_intent.succeeded"
        assert response["processed"] is True
        
        # Assert one-time purchase was processed
        mock_credit_service.get_user_by_stripe_customer_id.assert_called_once_with("cus_1234567890")
        mock_stripe_service.analyze_transaction.assert_called_once()
        mock_credit_service.purchase_one_time_credits.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('stripe.Webhook.construct_event', side_effect=ValueError("Invalid payload"))
    async def test_handle_invalid_payload(self, mock_construct_event):
        """Test handling an invalid webhook payload."""
        # This would be imported from the webhook router in your actual implementation
        from app.routers.stripe_webhook import stripe_webhook_handler
        
        # Create mock request with signature
        payload = "invalid json"
        stripe_signature = generate_stripe_signature(payload, "whsec_REMOVED_secret")
        
        # Create mock request object
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"Stripe-Signature": stripe_signature}
        mock_request.body.return_value = payload.encode('utf-8')
        
        # Create mock background tasks
        mock_background_tasks = MagicMock(spec=BackgroundTasks)
        
        # Create mock database
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Call the webhook handler and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await stripe_webhook_handler(
                request=mock_request,
                background_tasks=mock_background_tasks,
                db=mock_db
            )
        
        # Assert correct error
        assert excinfo.value.status_code == 400
        assert "Invalid payload" in str(excinfo.value.detail)
    
    @pytest.mark.asyncio
    @patch('stripe.Webhook.construct_event', side_effect=Exception("Unknown event type"))
    async def test_handle_unknown_event_type(self, mock_construct_event):
        """Test handling an unknown event type."""
        # This would be imported from the webhook router in your actual implementation
        from app.routers.stripe_webhook import stripe_webhook_handler
        
        # Create mock request with signature
        payload = json.dumps({"type": "unknown.event"})
        stripe_signature = generate_stripe_signature(payload, "whsec_REMOVED_secret")
        
        # Create mock request object
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"Stripe-Signature": stripe_signature}
        mock_request.body.return_value = payload.encode('utf-8')
        
        # Create mock background tasks
        mock_background_tasks = MagicMock(spec=BackgroundTasks)
        
        # Create mock database
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Call the webhook handler and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await stripe_webhook_handler(
                request=mock_request,
                background_tasks=mock_background_tasks,
                db=mock_db
            )
        
        # Assert correct error
        assert excinfo.value.status_code == 400
        assert "Error" in str(excinfo.value.detail)