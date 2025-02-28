"""Tests for Stripe integration functionality."""

import json
import pytest
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stripe_service import StripeService
from app.schemas.stripe_schemas import StripeTransactionRequest, StripeTransactionResponse
from app.core.config import settings


# Fixtures and mocks
@pytest.fixture
def mock_stripe_payment_intent():
    """Mock Stripe payment intent object."""
    return {
        "id": "pi_1234567890",
        "object": "payment_intent",
        "amount": 2999,  # $29.99
        "currency": "usd",
        "status": "succeeded",
        "customer": "cus_1234567890",
        "created": int(datetime.now(UTC).timestamp()) - 3600,  # 1 hour ago
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


@pytest.fixture
def mock_stripe_subscription():
    """Mock Stripe subscription object."""
    return {
        "id": "sub_1234567890",
        "object": "subscription",
        "customer": "cus_1234567890",
        "current_period_start": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
        "current_period_end": int(datetime.now(UTC).timestamp()) + 2592000,  # 30 days from now
        "status": "active",
        "created": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
        "items": {
            "data": [
                {
                    "id": "si_1234567890",
                    "plan": {
                        "id": "price_1234567890",
                        "product": "prod_1234567890",
                        "amount": 4999,  # $49.99
                        "currency": "usd"
                    }
                }
            ]
        },
        "cancel_at_period_end": False
    }


@pytest.fixture
def mock_stripe_customer():
    """Mock Stripe customer object."""
    return {
        "id": "cus_1234567890",
        "email": "customer@example.com",
        "name": "Test Customer",
        "created": int(datetime.now(UTC).timestamp()) - 86400,  # 1 day ago
    }


@pytest.fixture
def mock_credit_service():
    """Mock credit service."""
    mock = AsyncMock()
    
    # Mock purchase_plan method
    mock.purchase_plan.return_value = (
        MagicMock(id=123, new_balance=Decimal('500.00')),
        MagicMock(id=456)
    )
    
    # Mock purchase_one_time_credits method
    mock.purchase_one_time_credits.return_value = MagicMock(
        id=789, 
        new_balance=Decimal('300.00')
    )
    
    # Mock get_user_subscriptions method
    mock.get_user_subscriptions.return_value = [
        MagicMock(id=456, user_id=1, plan_id=100, is_active=True, auto_renew=True)
    ]
    
    return mock


@pytest.fixture
def mock_user_service():
    """Mock user service."""
    mock = AsyncMock()
    mock.get_user_by_id.return_value = MagicMock(
        id=1, 
        email="test@example.com", 
        username="testuser"
    )
    return mock


class TestStripeService:
    """Tests for the StripeService class."""
    
    @pytest.mark.asyncio
    @patch('stripe.PaymentIntent.retrieve')
    async def test_find_transaction_by_id_payment_intent(self, mock_retrieve, mock_stripe_payment_intent):
        """Test finding a transaction by ID when it's a PaymentIntent."""
        # Set up the mock
        mock_retrieve.return_value = mock_stripe_payment_intent
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        transaction = await service.find_transaction_by_id("pi_1234567890")
        
        # Assert
        assert transaction is not None
        assert transaction["id"] == "pi_1234567890"
        assert transaction["object_type"] == "payment_intent"
        assert transaction["amount"] == Decimal('29.99')  # $29.99 (2999 cents)
        assert transaction["customer_id"] == "cus_1234567890"
        assert transaction["customer_email"] == "customer@example.com"
    
    @pytest.mark.asyncio
    @patch('stripe.PaymentIntent.retrieve', side_effect=Exception("Not found"))
    @patch('stripe.Subscription.retrieve')
    async def test_find_transaction_by_id_subscription(self, mock_retrieve, mock_error, mock_stripe_subscription):
        """Test finding a transaction by ID when it's a Subscription."""
        # Set up the mock
        mock_retrieve.return_value = mock_stripe_subscription
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        transaction = await service.find_transaction_by_id("sub_1234567890")
        
        # Assert
        assert transaction is not None
        assert transaction["id"] == "sub_1234567890"
        assert transaction["object_type"] == "subscription"
        assert transaction["amount"] == Decimal('49.99')  # $49.99 (4999 cents)
        assert transaction["subscription_id"] == "sub_1234567890"
        assert transaction["customer_id"] == "cus_1234567890"
    
    @pytest.mark.asyncio
    @patch('stripe.PaymentIntent.retrieve', side_effect=Exception("Not found"))
    @patch('stripe.Subscription.retrieve', side_effect=Exception("Not found"))
    @patch('stripe.Charge.retrieve', side_effect=Exception("Not found"))
    @patch('stripe.Invoice.retrieve', side_effect=Exception("Not found"))
    async def test_find_transaction_by_id_not_found(self, mock_invoice, mock_charge, mock_subscription, mock_payment):
        """Test finding a transaction by ID when it's not found."""
        # Initialize service
        service = StripeService()
        
        # Call the method
        transaction = await service.find_transaction_by_id("nonexistent_id")
        
        # Assert
        assert transaction is None
    
    @pytest.mark.asyncio
    @patch('stripe.Customer.list')
    @patch('stripe.PaymentIntent.list')
    async def test_find_transactions_by_email(self, mock_pi_list, mock_cust_list, mock_stripe_customer, mock_stripe_payment_intent):
        """Test finding transactions by email."""
        # Set up the mocks
        mock_cust_list.return_value = MagicMock(data=[mock_stripe_customer])
        mock_pi_list.return_value = MagicMock(data=[mock_stripe_payment_intent])
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        transactions = await service.find_transactions_by_email("customer@example.com")
        
        # Assert
        assert transactions is not None
        assert len(transactions) == 1
        assert transactions[0]["id"] == "pi_1234567890"
        assert transactions[0]["customer_id"] == "cus_1234567890"
        assert transactions[0]["amount"] == Decimal('29.99')
    
    @pytest.mark.asyncio
    @patch('stripe.Customer.list')
    async def test_find_transactions_by_email_no_customers(self, mock_cust_list):
        """Test finding transactions by email when no customers are found."""
        # Set up the mock
        mock_cust_list.return_value = MagicMock(data=[])
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        transactions = await service.find_transactions_by_email("nonexistent@example.com")
        
        # Assert
        assert transactions == []
    
    @pytest.mark.asyncio
    async def test_analyze_transaction_oneoff(self, mock_stripe_payment_intent):
        """Test analyzing a one-time purchase transaction."""
        # Initialize service
        service = StripeService()
        
        # Format the transaction
        transaction = service._format_transaction(mock_stripe_payment_intent)
        
        # Call the method
        analysis = await service.analyze_transaction(transaction)
        
        # Assert
        assert analysis["transaction_type"] == "oneoff"
        assert analysis["recurring"] is False
        assert analysis["amount"] == Decimal('29.99')
        assert analysis["customer_id"] == "cus_1234567890"
        assert analysis["product_id"] == "prod_oneoff_credits"
    
    @pytest.mark.asyncio
    async def test_analyze_transaction_subscription(self, mock_stripe_subscription):
        """Test analyzing a subscription transaction."""
        # Initialize service
        service = StripeService()
        
        # Format the transaction
        transaction = service._format_transaction(mock_stripe_subscription)
        
        # Call the method
        analysis = await service.analyze_transaction(transaction)
        
        # Assert
        assert analysis["transaction_type"] == "subscription"
        assert analysis["recurring"] is True
        assert analysis["amount"] == Decimal('49.99')
        assert analysis["customer_id"] == "cus_1234567890"
        assert analysis["subscription_id"] == "sub_1234567890"
        assert analysis["plan_id"] == "price_1234567890"
        assert analysis["product_id"] == "prod_1234567890"
    
    @pytest.mark.asyncio
    @patch('stripe.Subscription.retrieve')
    @patch('stripe.Subscription.modify')
    async def test_handle_subscription_renewal(self, mock_modify, mock_retrieve, mock_stripe_subscription):
        """Test handling subscription renewal."""
        # Set up the mocks
        mock_retrieve.return_value = {**mock_stripe_subscription, "cancel_at_period_end": True}
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        result = await service.handle_subscription_renewal("sub_1234567890")
        
        # Assert
        assert result is True
        mock_modify.assert_called_once_with("sub_1234567890", cancel_at_period_end=False)
    
    @pytest.mark.asyncio
    @patch('stripe.Subscription.retrieve')
    @patch('stripe.Subscription.modify')
    async def test_cancel_subscription(self, mock_modify, mock_retrieve, mock_stripe_subscription):
        """Test cancelling a subscription."""
        # Set up the mocks
        mock_retrieve.return_value = mock_stripe_subscription
        
        # Initialize service
        service = StripeService()
        
        # Call the method
        result = await service.cancel_subscription("sub_1234567890")
        
        # Assert
        assert result is True
        mock_modify.assert_called_once_with("sub_1234567890", cancel_at_period_end=True)


class TestStripeEndpoints:
    """Tests for the Stripe integration endpoints."""
    
    @pytest.mark.asyncio
    @patch('app.routers.credit_router.StripeService')
    @patch('app.routers.credit_router.CreditService')
    @patch('app.routers.credit_router.UserService')
    async def test_add_credits_from_stripe_subscription(
        self, 
        mock_user_service_class, 
        mock_credit_service_class, 
        mock_stripe_service_class,
        mock_user_service,
        mock_credit_service,
        mock_stripe_subscription
    ):
        """Test adding credits from a Stripe subscription."""
        from app.routers.credit_router import add_credits_from_stripe
        
        # Set up the mocks
        mock_user_service_class.return_value = mock_user_service
        mock_credit_service_class.return_value = mock_credit_service
        
        # Mock StripeService methods
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up transaction data
        transaction_data = {
            "id": "sub_1234567890",
            "object_type": "subscription",
            "amount": Decimal('49.99'),
            "subscription_id": "sub_1234567890",
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "created_at": datetime.now(UTC),
        }
        
        # Set up analysis result
        analysis_result = {
            "transaction_type": "subscription",
            "recurring": True,
            "amount": Decimal('49.99'),
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "subscription_id": "sub_1234567890",
            "plan_id": "price_1234567890",
            "product_id": "prod_1234567890",
            "transaction_id": "sub_1234567890",
            "created_at": datetime.now(UTC),
        }
        
        # Mock database query for plan
        mock_db = AsyncMock()
        mock_db.execute.return_value = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = 100  # plan_id
        
        # Set up Stripe service mock responses
        mock_stripe_service.find_transaction_by_id.return_value = transaction_data
        mock_stripe_service.analyze_transaction.return_value = analysis_result
        mock_stripe_service.handle_subscription_renewal.return_value = True
        
        # Create request
        request = StripeTransactionRequest(
            transaction_id="sub_1234567890",
            transaction_type="subscription"
        )
        
        # Mock current user
        current_user = MagicMock(id=1)
        
        # Mock background tasks
        background_tasks = MagicMock()
        
        # Call the endpoint
        response = await add_credits_from_stripe(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            db=mock_db
        )
        
        # Assert
        assert isinstance(response, StripeTransactionResponse)
        assert response.applied is True
        assert response.transaction.transaction_id == "sub_1234567890"
        assert response.transaction.transaction_type == "subscription"
        assert response.transaction.amount == Decimal('49.99')
        assert response.subscription_id == 456
        assert response.credit_transaction_id == 123
        assert response.new_balance == Decimal('500.00')
        
        # Assert correct services were called
        mock_user_service.get_user_by_id.assert_called_once_with(1)
        mock_stripe_service.find_transaction_by_id.assert_called_once_with("sub_1234567890")
        mock_stripe_service.analyze_transaction.assert_called_once_with(transaction_data)
        mock_credit_service.purchase_plan.assert_called_once()
        mock_stripe_service.handle_subscription_renewal.assert_called_once_with("sub_1234567890")
    
    @pytest.mark.asyncio
    @patch('app.routers.credit_router.StripeService')
    @patch('app.routers.credit_router.CreditService')
    @patch('app.routers.credit_router.UserService')
    async def test_add_credits_from_stripe_oneoff(
        self, 
        mock_user_service_class, 
        mock_credit_service_class, 
        mock_stripe_service_class,
        mock_user_service,
        mock_credit_service,
        mock_stripe_payment_intent
    ):
        """Test adding credits from a one-time Stripe payment."""
        from app.routers.credit_router import add_credits_from_stripe
        
        # Set up the mocks
        mock_user_service_class.return_value = mock_user_service
        mock_credit_service_class.return_value = mock_credit_service
        
        # Mock StripeService methods
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up transaction data
        transaction_data = {
            "id": "pi_1234567890",
            "object_type": "payment_intent",
            "amount": Decimal('29.99'),
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "created_at": datetime.now(UTC),
        }
        
        # Set up analysis result
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
        
        # Mock database
        mock_db = AsyncMock()
        
        # Set up Stripe service mock responses
        mock_stripe_service.find_transaction_by_id.return_value = transaction_data
        mock_stripe_service.analyze_transaction.return_value = analysis_result
        
        # Create request
        request = StripeTransactionRequest(
            transaction_id="pi_1234567890",
            transaction_type="oneoff"
        )
        
        # Mock current user
        current_user = MagicMock(id=1)
        
        # Mock background tasks
        background_tasks = MagicMock()
        
        # Call the endpoint
        response = await add_credits_from_stripe(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            db=mock_db
        )
        
        # Assert
        assert isinstance(response, StripeTransactionResponse)
        assert response.applied is True
        assert response.transaction.transaction_id == "pi_1234567890"
        assert response.transaction.transaction_type == "oneoff"
        assert response.transaction.amount == Decimal('29.99')
        assert response.subscription_id is None
        assert response.credit_transaction_id == 789
        assert response.new_balance == Decimal('300.00')
        
        # Assert correct services were called
        mock_user_service.get_user_by_id.assert_called_once_with(1)
        mock_stripe_service.find_transaction_by_id.assert_called_once_with("pi_1234567890")
        mock_stripe_service.analyze_transaction.assert_called_once_with(transaction_data)
        mock_credit_service.purchase_one_time_credits.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('app.routers.credit_router.StripeService')
    @patch('app.routers.credit_router.CreditService')
    @patch('app.routers.credit_router.UserService')
    async def test_add_credits_from_stripe_by_email(
        self, 
        mock_user_service_class, 
        mock_credit_service_class, 
        mock_stripe_service_class,
        mock_user_service,
        mock_credit_service,
        mock_stripe_payment_intent
    ):
        """Test adding credits from Stripe using email lookup."""
        from app.routers.credit_router import add_credits_from_stripe
        
        # Set up the mocks
        mock_user_service_class.return_value = mock_user_service
        mock_credit_service_class.return_value = mock_credit_service
        
        # Mock StripeService methods
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up transaction data (same as payment intent test)
        transaction_data = {
            "id": "pi_1234567890",
            "object_type": "payment_intent",
            "amount": Decimal('29.99'),
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "created_at": datetime.now(UTC),
        }
        
        # Set up analysis result (same as payment intent test)
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
        
        # Mock database
        mock_db = AsyncMock()
        
        # Set up Stripe service mock responses for email lookup
        mock_stripe_service.find_transactions_by_email.return_value = [transaction_data]
        mock_stripe_service.analyze_transaction.return_value = analysis_result
        
        # Create request with email instead of transaction_id
        request = StripeTransactionRequest(
            email="customer@example.com",
            transaction_type="oneoff"
        )
        
        # Mock current user
        current_user = MagicMock(id=1)
        
        # Mock background tasks
        background_tasks = MagicMock()
        
        # Call the endpoint
        response = await add_credits_from_stripe(
            request=request,
            background_tasks=background_tasks,
            current_user=current_user,
            db=mock_db
        )
        
        # Assert
        assert isinstance(response, StripeTransactionResponse)
        assert response.applied is True
        assert response.transaction.transaction_id == "pi_1234567890"
        assert response.transaction.transaction_type == "oneoff"
        
        # Assert correct services were called
        mock_user_service.get_user_by_id.assert_called_once_with(1)
        mock_stripe_service.find_transactions_by_email.assert_called_once_with("customer@example.com")
        mock_stripe_service.analyze_transaction.assert_called_once_with(transaction_data)
    
    @pytest.mark.asyncio
    @patch('app.routers.credit_router.StripeService')
    @patch('app.routers.credit_router.CreditService')
    @patch('app.routers.credit_router.UserService')
    async def test_add_credits_from_stripe_transaction_not_found(
        self, 
        mock_user_service_class, 
        mock_credit_service_class, 
        mock_stripe_service_class,
        mock_user_service,
        mock_credit_service
    ):
        """Test adding credits when the transaction is not found."""
        from app.routers.credit_router import add_credits_from_stripe
        
        # Set up the mocks
        mock_user_service_class.return_value = mock_user_service
        mock_credit_service_class.return_value = mock_credit_service
        
        # Mock StripeService methods
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up Stripe service mock responses
        mock_stripe_service.find_transaction_by_id.return_value = None
        
        # Mock database
        mock_db = AsyncMock()
        
        # Create request
        request = StripeTransactionRequest(
            transaction_id="nonexistent_id",
            transaction_type="oneoff"
        )
        
        # Mock current user
        current_user = MagicMock(id=1)
        
        # Mock background tasks
        background_tasks = MagicMock()
        
        # Call the endpoint and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await add_credits_from_stripe(
                request=request,
                background_tasks=background_tasks,
                current_user=current_user,
                db=mock_db
            )
        
        # Assert correct error
        assert excinfo.value.status_code == 404
        assert "Transaction not found" in str(excinfo.value.detail)
    
    @pytest.mark.asyncio
    @patch('app.routers.credit_router.StripeService')
    @patch('app.routers.credit_router.CreditService')
    @patch('app.routers.credit_router.UserService')
    async def test_add_credits_from_stripe_transaction_type_mismatch(
        self, 
        mock_user_service_class, 
        mock_credit_service_class, 
        mock_stripe_service_class,
        mock_user_service,
        mock_credit_service,
        mock_stripe_subscription
    ):
        """Test adding credits when transaction type doesn't match the requested type."""
        from app.routers.credit_router import add_credits_from_stripe
        
        # Set up the mocks
        mock_user_service_class.return_value = mock_user_service
        mock_credit_service_class.return_value = mock_credit_service
        
        # Mock StripeService methods
        mock_stripe_service = AsyncMock()
        mock_stripe_service_class.return_value = mock_stripe_service
        
        # Set up transaction data
        transaction_data = {
            "id": "sub_1234567890",
            "object_type": "subscription",
            "amount": Decimal('49.99'),
            "subscription_id": "sub_1234567890",
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "created_at": datetime.now(UTC),
        }
        
        # Set up analysis result with subscription type
        analysis_result = {
            "transaction_type": "subscription",  # This will mismatch with "oneoff" in the request
            "recurring": True,
            "amount": Decimal('49.99'),
            "customer_id": "cus_1234567890",
            "customer_email": "customer@example.com",
            "subscription_id": "sub_1234567890",
            "plan_id": "price_1234567890",
            "product_id": "prod_1234567890",
            "transaction_id": "sub_1234567890",
            "created_at": datetime.now(UTC),
        }
        
        # Mock database
        mock_db = AsyncMock()
        
        # Set up Stripe service mock responses
        mock_stripe_service.find_transaction_by_id.return_value = transaction_data
        mock_stripe_service.analyze_transaction.return_value = analysis_result
        
        # Create request with mismatched type
        request = StripeTransactionRequest(
            transaction_id="sub_1234567890",
            transaction_type="oneoff"  # This will mismatch with "subscription" in the analysis
        )
        
        # Mock current user
        current_user = MagicMock(id=1)
        
        # Mock background tasks
        background_tasks = MagicMock()
        
        # Call the endpoint and expect exception
        with pytest.raises(HTTPException) as excinfo:
            await add_credits_from_stripe(
                request=request,
                background_tasks=background_tasks,
                current_user=current_user,
                db=mock_db
            )
        
        # Assert correct error
        assert excinfo.value.status_code == 400
        assert "Transaction type mismatch" in str(excinfo.value.detail)