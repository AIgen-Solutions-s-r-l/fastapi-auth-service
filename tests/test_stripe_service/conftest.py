import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timezone
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
import stripe

from app.services.stripe_service import StripeService
from app.core.config import settings
from app.models.plan import Subscription as SubscriptionModel


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
def mock_db_session() -> AsyncSession: # Changed order to define before use
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
def stripe_service(mock_db_session: AsyncSession):
    """Fixture to create a StripeService instance with a mocked DB session."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
        # Ensure stripe.api_key is set if StripeService relies on global stripe state during init
        # or if any direct stripe calls are made outside of methods using asyncio.to_thread
        original_api_key = stripe.api_key
        stripe.api_key = settings.STRIPE_SECRET_KEY 
        service = StripeService(db_session=mock_db_session)
        stripe.api_key = original_api_key # Restore original key
        return service

@pytest.fixture
def stripe_service_with_db(mock_db_session: AsyncSession): # Changed order
    """Fixture to create a StripeService instance with a mocked DB session."""
    # Patch settings to avoid actual key validation during tests
    with patch('app.services.stripe_service.settings', MagicMock(STRIPE_SECRET_KEY='test_key', STRIPE_API_VERSION='test_version')):
        original_api_key = stripe.api_key
        stripe.api_key = settings.STRIPE_SECRET_KEY
        service = StripeService(db_session=mock_db_session)
        stripe.api_key = original_api_key
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

@pytest.fixture
def mock_datetime_now(mocker):
    """Fixture to mock datetime.now."""
    mock_now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Patching datetime in the context of the stripe_service module if that's where it's used.
    # If datetime is imported directly in stripe_service.py as `from datetime import datetime`
    # then this path needs to be precise.
    # Assuming it's used like `datetime.now()` within stripe_service.py:
    mocker.patch('app.services.stripe_service.datetime', MagicMock(now=MagicMock(return_value=mock_now)))
    return mock_now