import pytest
import stripe
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator, Generator, Any, Dict, Callable

from fastapi import FastAPI, Request, HTTPException, Header
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app as main_app # Assuming your FastAPI app instance is here
from app.models.user import User
from app.models.processed_event import ProcessedStripeEvent
from app.services.webhook_service import WebhookService
from app.routers.webhooks.stripe_webhooks import verify_stripe_signature, stripe_webhook_endpoint

# Set a dummy webhook secret for testing if not already set
settings.STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET or "whsec_REMOVED_dummysecret"
settings.STRIPE_SECRET_KEY = settings.STRIPE_SECRET_KEY or "sk_test_dummykey"
stripe.api_key = settings.STRIPE_SECRET_KEY


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Test client for making requests to the FastAPI application.
    Overrides dependencies like get_db.
    """
    async with AsyncClient(app=main_app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mocks the SQLAlchemy AsyncSession with improved async handling."""
    session = AsyncMock(spec=AsyncSession)
    
    # Mock the execute method to return an object that has scalars() -> first() chain
    mock_execute_result = AsyncMock()
    mock_scalars_result = AsyncMock()
    mock_scalars_result.first = AsyncMock(return_value=None) # Default: not found
    mock_execute_result.scalars = MagicMock(return_value=mock_scalars_result)
    session.execute = AsyncMock(return_value=mock_execute_result)

    # Mock other methods as AsyncMock
    session.commit = AsyncMock()
    session.rollback = AsyncMock() # Make rollback async
    session.add = MagicMock() # Keep add sync if it doesn't need await
    session.merge = AsyncMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None) # Default get returns None
    session.scalar_one_or_none = AsyncMock(return_value=None) # Default scalar_one_or_none returns None
    
    # Allow configuring the mock result dynamically in tests
    session.mock_execute_result = mock_execute_result
    session.mock_scalars_result = mock_scalars_result

    return session


@pytest.fixture
def webhook_service(mock_db_session: AsyncMock) -> WebhookService:
    """Fixture for WebhookService with a mocked DB session."""
    return WebhookService(db_session=mock_db_session)


@pytest.fixture
def mock_stripe_event_factory() -> Callable[[str, Dict[str, Any]], stripe.Event]:
    """Factory to create mock Stripe events."""
    def _factory(event_type: str, data_object: Dict[str, Any], event_id: str = "evt_test_event") -> stripe.Event:
        event_data = {
            "id": event_id,
            "object": "event",
            "api_version": "2020-08-27", # Use a relevant API version
            "created": 1600000000,
            "data": {"object": data_object},
            "livemode": False,
            "pending_webhooks": 0,
            "request": {"id": "req_test_request", "idempotency_key": None},
            "type": event_type,
        }
        return stripe.Event.construct_from(event_data, settings.STRIPE_SECRET_KEY)
    return _factory


@pytest.fixture
def mock_user() -> User:
    """Fixture for a mock User object."""
    # Initialize without kwargs that are not in __init__
    user = User(
        id="test_user_123",
        email="test@example.com",
        hashed_password="hashed_password",
        stripe_customer_id="cus_testcustomer",
    )
    # Set other attributes directly
    user.is_active=True
    user.is_verified=True
    user.account_status="active"
    user.has_consumed_initial_trial=False
    return user

@pytest.fixture
def mock_processed_event() -> ProcessedStripeEvent:
    """Fixture for a mock ProcessedStripeEvent object."""
    # Initialize without kwargs that are not in __init__
    event = ProcessedStripeEvent(
        stripe_event_id="evt_test_already_processed",
        event_type="checkout.session.completed"
    )
    # Set created_at if needed, though it has a default
    # event.created_at = datetime.fromisoformat("2023-01-01T12:00:00Z")
    return event


# Basic test to ensure fixtures are working
def test_fixture_setup(webhook_service: WebhookService, mock_stripe_event_factory: Callable):
    assert webhook_service is not None
    assert webhook_service.db is not None
    event = mock_stripe_event_factory("test.event", {"id": "obj_test"})
    assert event.type == "test.event"
    assert event.id.startswith("evt_")

# Tests for verify_stripe_signature
@pytest.mark.asyncio
async def test_verify_stripe_signature_valid(mock_stripe_event_factory: Callable):
    """Test verify_stripe_signature with a valid signature."""
    payload_dict = {"id": "evt_test_payload", "object": "event", "type": "test.event.valid"}
    payload_bytes = b'{"id": "evt_test_payload", "object": "event", "type": "test.event.valid"}' # Example payload
    
    # This is a simplified way to get a "valid" signature for testing purposes.
    # In a real scenario, Stripe SDK generates this. We mock construct_event.
    timestamp = "1600000000" # Example timestamp
    signature_payload = f"{timestamp}.{payload_bytes.decode()}"
    # For testing, we don't need a real crypto signature if we mock construct_event
    mock_signature = f"t={timestamp},v1=dummy_signature_v1"

    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)
    
    expected_event = mock_stripe_event_factory("test.event.valid", payload_dict, event_id="evt_test_payload")

    with patch("stripe.Webhook.construct_event", return_value=expected_event) as mock_construct:
        event = await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        mock_construct.assert_called_once_with(
            payload_bytes, mock_signature, settings.STRIPE_WEBHOOK_SECRET
        )
        assert event is not None
        assert event.id == "evt_test_payload"
        assert event.type == "test.event.valid"

@pytest.mark.asyncio
async def test_verify_stripe_signature_missing_header():
    """Test verify_stripe_signature with a missing Stripe-Signature header."""
    mock_request = AsyncMock(spec=Request)
    with pytest.raises(HTTPException) as exc_info:
        await verify_stripe_signature(request=mock_request, stripe_signature=None)
    assert exc_info.value.status_code == 400
    assert "Stripe-Signature header missing" in exc_info.value.detail

@pytest.mark.asyncio
async def test_verify_stripe_signature_missing_secret(monkeypatch):
    """Test verify_stripe_signature when STRIPE_WEBHOOK_SECRET is not set."""
    mock_request = AsyncMock(spec=Request)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    with pytest.raises(HTTPException) as exc_info:
        await verify_stripe_signature(request=mock_request, stripe_signature="t=123,v1=dummy")
    assert exc_info.value.status_code == 500
    assert "Webhook secret not configured" in exc_info.value.detail
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_REMOVED_dummysecret") # Restore

@pytest.mark.asyncio
async def test_verify_stripe_signature_invalid_payload():
    """Test verify_stripe_signature with an invalid payload (ValueError from construct_event)."""
    payload_bytes = b"invalid json"
    mock_signature = "t=123,v1=dummy"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)

    with patch("stripe.Webhook.construct_event", side_effect=ValueError("Invalid payload")) as mock_construct:
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        mock_construct.assert_called_once_with(
            payload_bytes, mock_signature, settings.STRIPE_WEBHOOK_SECRET
        )
        assert exc_info.value.status_code == 400
        assert "Invalid payload" in exc_info.value.detail

@pytest.mark.asyncio
async def test_verify_stripe_signature_invalid_signature_error():
    """Test verify_stripe_signature with a SignatureVerificationError from construct_event."""
    payload_bytes = b'{"id": "evt_test"}'
    mock_signature = "t=123,v1=invalid_signature"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)

    with patch("stripe.Webhook.construct_event", side_effect=stripe.error.SignatureVerificationError("Invalid signature", "sig_header")) as mock_construct:
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        mock_construct.assert_called_once_with(
            payload_bytes, mock_signature, settings.STRIPE_WEBHOOK_SECRET
        )
        assert exc_info.value.status_code == 400
        assert "Invalid signature" in exc_info.value.detail

@pytest.mark.asyncio
async def test_verify_stripe_signature_unexpected_error():
    """Test verify_stripe_signature with an unexpected error from construct_event."""
    payload_bytes = b'{"id": "evt_test"}'
    mock_signature = "t=123,v1=dummy"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)

    with patch("stripe.Webhook.construct_event", side_effect=Exception("Unexpected error")) as mock_construct:
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        mock_construct.assert_called_once_with(
            payload_bytes, mock_signature, settings.STRIPE_WEBHOOK_SECRET
        )
        assert exc_info.value.status_code == 500
        assert "Error verifying webhook signature" in exc_info.value.detail
# Tests for WebhookService idempotency
@pytest.mark.asyncio
async def test_webhook_service_is_event_processed_true(
    webhook_service: WebhookService,
    mock_processed_event: ProcessedStripeEvent
):
    """Test is_event_processed when event is already processed."""
    event_id = "evt_test_already_processed"
    # Configure the mock_db_session.execute().scalars().first() chain
    webhook_service.db.mock_scalars_result.first.return_value = mock_processed_event
    
    result = await webhook_service.is_event_processed(event_id)
    
    webhook_service.db.execute.assert_called_once()
    # We can add more specific assertion on the SQL statement if needed, by inspecting call_args
    assert result is True

@pytest.mark.asyncio
async def test_webhook_service_is_event_processed_false(webhook_service: WebhookService):
    """Test is_event_processed when event is not processed."""
    event_id = "evt_test_new_event"
    # Ensure the mock_db_session.execute().scalars().first() returns None (default fixture behavior)
    webhook_service.db.mock_scalars_result.first.return_value = None
        
    result = await webhook_service.is_event_processed(event_id)
    
    webhook_service.db.execute.assert_called_once()
    assert result is False

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_success(webhook_service: WebhookService):
    """Test mark_event_as_processed successfully marks an event."""
    event_id = "evt_test_mark_success"
    event_type = "checkout.session.completed"
    
    await webhook_service.mark_event_as_processed(event_id, event_type)
    
    # Check that execute (for pg_insert) and commit were called
    webhook_service.db.execute.assert_called_once()
    # Example of how you might check the statement if it were simpler or you capture it:
    # called_stmt = webhook_service.db.execute.call_args[0][0]
    # assert "processed_stripe_events" in str(called_stmt).lower()
    # assert event_id in str(called_stmt)
    webhook_service.db.commit.assert_called_once()
    webhook_service.db.rollback.assert_not_called()

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_integrity_error_simulated(
    webhook_service: WebhookService
):
    """
    Test mark_event_as_processed handles IntegrityError (simulated by on_conflict_do_nothing).
    In reality, pg_insert with on_conflict_do_nothing should not raise IntegrityError for duplicates.
    This test rather ensures commit is called and rollback is not, as the DB handles the conflict.
    """
    event_id = "evt_test_mark_duplicate"
    event_type = "checkout.session.completed"

    # No specific side effect needed for execute if on_conflict_do_nothing works
    # as it won't raise an error that Python catches as IntegrityError here.
    # The DB handles it.

    await webhook_service.mark_event_as_processed(event_id, event_type)

    webhook_service.db.execute.assert_called_once()
    webhook_service.db.commit.assert_called_once() # Commit should still be called
    webhook_service.db.rollback.assert_not_called() # Rollback should not be called

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_sqlalchemy_error(
    webhook_service: WebhookService
):
    """Test mark_event_as_processed handles general SQLAlchemyError."""
    from sqlalchemy.exc import SQLAlchemyError # Import specific error

    event_id = "evt_test_mark_db_error"
    event_type = "checkout.session.completed"
    
    # Simulate SQLAlchemyError on execute
    webhook_service.db.execute.side_effect = SQLAlchemyError("Simulated DB connection error")
    
    with pytest.raises(SQLAlchemyError, match="Simulated DB connection error"): # Check for the specific error
        await webhook_service.mark_event_as_processed(event_id, event_type)
    
    webhook_service.db.execute.assert_called_once()
    webhook_service.db.commit.assert_not_called()
    webhook_service.db.rollback.assert_called_once() # Check async rollback
# Tests for WebhookService.handle_checkout_session_completed
@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent")
@patch("app.services.webhook_service.stripe.SetupIntent")
@patch("app.services.webhook_service.stripe.Subscription") # For potential cancellation
async def test_handle_checkout_session_completed_unique_fingerprint(
    mock_stripe_sub_cancel: MagicMock,
    mock_stripe_setup_intent: MagicMock,
    mock_stripe_payment_intent: MagicMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test handle_checkout_session_completed with a unique card fingerprint."""
    event_id = "evt_checkout_unique_fp"
    user_id = mock_user.id
    stripe_customer_id = "cus_test_unique_fp"
    stripe_subscription_id = "sub_test_unique_fp_sub"
    card_fingerprint = "fp_unique_checkout"

    checkout_session_data = {
        "id": "cs_test_unique_fp",
        "object": "checkout.session",
        "client_reference_id": user_id,
        "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, # Assume a subscription is created
        "payment_intent": "pi_test_unique_fp",
        "metadata": {"user_id": user_id} # Ensure metadata is also checked
    }
    event = mock_stripe_event_factory(
        "checkout.session.completed", checkout_session_data, event_id=event_id
    )

    # Mock get_card_fingerprint_from_event to return a unique fingerprint
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    
    # Mock DB: No existing fingerprint
    webhook_service.db.mock_scalars_result.first.return_value = None
    # Mock DB: User found for status update (though not strictly needed for unique case here)
    webhook_service.db.get.return_value = mock_user

    await webhook_service.handle_checkout_session_completed(event)

    webhook_service.get_card_fingerprint_from_event.assert_called_once_with(event.data.object, event_id)
    # Check that DB was queried for existing fingerprint
    assert webhook_service.db.execute.call_count == 1 # Only one select for fingerprint
    
    # No cancellation, no user status change to rejected, no block event
    mock_stripe_sub_cancel.delete.assert_not_called()
    assert mock_user.account_status != "trial_rejected" # Assuming it was 'active' or something else initially
    # Patch the specific publisher method for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish.assert_not_called()
    webhook_service.db.commit.assert_not_called() # No commit if no changes were made by this handler directly

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent")
@patch("app.services.webhook_service.stripe.SetupIntent")
@patch("app.services.webhook_service.stripe.Subscription.delete") # Mock specific delete
async def test_handle_checkout_session_completed_duplicate_fingerprint(
    mock_stripe_sub_delete: MagicMock,
    mock_stripe_setup_intent: MagicMock,
    mock_stripe_payment_intent: MagicMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User # Use the fixture
):
    """Test handle_checkout_session_completed with a duplicate card fingerprint."""
    event_id = "evt_checkout_duplicate_fp"
    user_id = mock_user.id
    stripe_customer_id = "cus_test_duplicate_fp"
    stripe_subscription_id = "sub_test_duplicate_fp_sub"
    card_fingerprint = "fp_duplicate_checkout"

    checkout_session_data = {
        "id": "cs_test_duplicate_fp",
        "object": "checkout.session",
        "client_reference_id": user_id,
        "customer": stripe_customer_id,
        "subscription": stripe_subscription_id,
        "payment_intent": "pi_test_duplicate_fp",
    }
    event = mock_stripe_event_factory(
        "checkout.session.completed", checkout_session_data, event_id=event_id
    )

    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    
    # Mock DB: Existing fingerprint found
    existing_fingerprint_mock = MagicMock(spec=ProcessedStripeEvent) # Can use any model for structure
    existing_fingerprint_mock.user_id = "other_user_id"
    existing_fingerprint_mock.stripe_subscription_id = "sub_other"
    webhook_service.db.mock_scalars_result.first.return_value = existing_fingerprint_mock
    
    # Mock DB: User found for status update
    webhook_service.db.get.return_value = mock_user
    original_status = mock_user.account_status


    # Mock event publisher
    # Patch the specific publisher method for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish:
        await webhook_service.handle_checkout_session_completed(event)

        webhook_service.get_card_fingerprint_from_event.assert_called_once_with(event.data.object, event_id)
        mock_stripe_sub_delete.assert_called_once_with(stripe_subscription_id)
        
        webhook_service.db.get.assert_called_once_with(User, user_id)
        assert mock_user.account_status == "trial_rejected"
        webhook_service.db.commit.assert_called_once() # Commit for user status change

        mock_publish.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )

    # Restore user status if needed for other tests, though fixtures usually handle this
    mock_user.account_status = original_status


@pytest.mark.asyncio
async def test_handle_checkout_session_completed_missing_user_id(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
):
    """Test handle_checkout_session_completed when user ID is missing from event."""
    event_id = "evt_checkout_no_user"
    checkout_session_data = {
        "id": "cs_test_no_user",
        "object": "checkout.session",
        "client_reference_id": None, # No user ID
        "customer": "cus_test_no_user",
        "subscription": "sub_test_no_user_sub",
        "payment_intent": "pi_test_no_user",
        "metadata": {} # No user_id in metadata either
    }
    event = mock_stripe_event_factory(
        "checkout.session.completed", checkout_session_data, event_id=event_id
    )

    # Mock get_card_fingerprint_from_event as it might still be called before user_id check
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value="fp_irrelevant")

    await webhook_service.handle_checkout_session_completed(event)

    # Ensure fingerprint retrieval is NOT called if user_id check is first
    # Based on current implementation, get_card_fingerprint_from_event is called AFTER user_id check.
    # So, if user_id is missing, get_card_fingerprint_from_event should not be called.
    # Let's adjust the service code or this test.
    # Current service code: user_id check is first. So get_card_fingerprint_from_event won't be called.
    webhook_service.get_card_fingerprint_from_event.assert_not_called()
    
    webhook_service.db.execute.assert_not_called() # No DB calls if user_id is missing
    webhook_service.db.commit.assert_not_called()
    # Patch the specific publisher method for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent") # For get_card_fingerprint
@patch("app.services.webhook_service.stripe.SetupIntent")   # For get_card_fingerprint
async def test_handle_checkout_session_completed_missing_fingerprint(
    mock_stripe_setup_intent: MagicMock,
    mock_stripe_payment_intent: MagicMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test handle_checkout_session_completed when card fingerprint cannot be retrieved."""
    event_id = "evt_checkout_no_fp"
    user_id = mock_user.id
    checkout_session_data = {
        "id": "cs_test_no_fp",
        "object": "checkout.session",
        "client_reference_id": user_id,
        "customer": "cus_test_no_fp",
        "subscription": "sub_test_no_fp_sub",
        "payment_intent": "pi_test_no_fp", # Assume this leads to no fingerprint
    }
    event = mock_stripe_event_factory(
        "checkout.session.completed", checkout_session_data, event_id=event_id
    )

    # Mock get_card_fingerprint_from_event to return None
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=None)
    
    # Mock DB: User found (though not strictly needed as it returns early)
    webhook_service.db.get.return_value = mock_user

    await webhook_service.handle_checkout_session_completed(event)

    webhook_service.get_card_fingerprint_from_event.assert_called_once_with(event.data.object, event_id)
    
    # No DB query for existing fingerprint if current one is None
    webhook_service.db.execute.assert_not_called() 
    webhook_service.db.commit.assert_not_called()
    # Patch the specific publisher method for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish.assert_not_called()

# Test for get_card_fingerprint_from_event itself
@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve")
@patch("app.services.webhook_service.stripe.SetupIntent.retrieve")
@patch("app.services.webhook_service.stripe.PaymentMethod.retrieve")
async def test_get_card_fingerprint_from_payment_intent(
    mock_pm_retrieve: MagicMock,
    mock_si_retrieve: MagicMock,
    mock_pi_retrieve: MagicMock,
    webhook_service: WebhookService
):
    event_data = {"payment_intent": "pi_123"}
    # Mock the nested structure correctly
    mock_pm_card = MagicMock()
    mock_pm_card.fingerprint = "fp_from_pi"
    mock_pm = MagicMock()
    mock_pm.card = mock_pm_card
    mock_pi = MagicMock()
    mock_pi.payment_method = mock_pm
    mock_pi_retrieve.return_value = mock_pi

    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
    assert fingerprint == "fp_from_pi"
    mock_pi_retrieve.assert_called_once_with("pi_123", expand=["payment_method"])
    mock_si_retrieve.assert_not_called()
    mock_pm_retrieve.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve")
@patch("app.services.webhook_service.stripe.SetupIntent.retrieve")
@patch("app.services.webhook_service.stripe.PaymentMethod.retrieve")
async def test_get_card_fingerprint_from_setup_intent(
    mock_pm_retrieve: MagicMock,
    mock_si_retrieve: MagicMock,
    mock_pi_retrieve: MagicMock,
    webhook_service: WebhookService
):
    event_data = {"setup_intent": "si_123"}
    # Mock the nested structure correctly
    mock_pm_card_si = MagicMock()
    mock_pm_card_si.fingerprint = "fp_from_si"
    mock_pm_si = MagicMock()
    mock_pm_si.card = mock_pm_card_si
    mock_si = MagicMock()
    mock_si.payment_method = mock_pm_si
    mock_si_retrieve.return_value = mock_si

    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
    assert fingerprint == "fp_from_si"
    mock_si_retrieve.assert_called_once_with("si_123", expand=["payment_method"])
    mock_pi_retrieve.assert_not_called()
    mock_pm_retrieve.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve")
@patch("app.services.webhook_service.stripe.SetupIntent.retrieve")
@patch("app.services.webhook_service.stripe.PaymentMethod.retrieve")
async def test_get_card_fingerprint_from_default_payment_method(
    mock_pm_retrieve: MagicMock,
    mock_si_retrieve: MagicMock,
    mock_pi_retrieve: MagicMock,
    webhook_service: WebhookService
):
    event_data = {"default_payment_method": "pm_123"} # e.g. from customer.subscription.created
    mock_pm = MagicMock()
    mock_pm.card.fingerprint = "fp_from_pm"
    mock_pm_retrieve.return_value = mock_pm

    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
    assert fingerprint == "fp_from_pm"
    mock_pm_retrieve.assert_called_once_with("pm_123")
    mock_pi_retrieve.assert_not_called()
    mock_si_retrieve.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve")
@patch("app.services.webhook_service.stripe.SetupIntent.retrieve")
@patch("app.services.webhook_service.stripe.PaymentMethod.retrieve")
async def test_get_card_fingerprint_from_event_data_direct(
    mock_pm_retrieve: MagicMock,
    mock_si_retrieve: MagicMock,
    mock_pi_retrieve: MagicMock,
    webhook_service: WebhookService
):
    event_data = {
        "payment_method_details": {
            "card": {
                "fingerprint": "fp_direct_on_event"
            }
        }
    }
    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
    assert fingerprint == "fp_direct_on_event"
    mock_pi_retrieve.assert_not_called()
    mock_si_retrieve.assert_not_called()
    mock_pm_retrieve.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve", side_effect=stripe.error.StripeError("API Error"))
async def test_get_card_fingerprint_stripe_api_error(
    mock_pi_retrieve: MagicMock,
    webhook_service: WebhookService
):
    event_data = {"payment_intent": "pi_error"}
    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test_api_error")
    assert fingerprint is None
    mock_pi_retrieve.assert_called_once()
# Tests for WebhookService.handle_customer_subscription_created
from app.models.plan import Subscription as DBSubscriptionModel, UsedTrialCardFingerprint
from app.models.credit import UserCredit, CreditTransaction, TransactionType as ModelTransactionType
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone, timedelta

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_non_trial(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test non-trial subscription creation."""
    event_id = "evt_sub_created_nontrial"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_nontrial_123"
    stripe_price_id = "price_nontrial_123"

    subscription_data = {
        "id": stripe_subscription_id,
        "object": "subscription",
        "customer": stripe_customer_id,
        "status": "active", # Non-trial, so directly active
        "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "trial_end": None, # Explicitly not a trial
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
        "metadata": {"user_id": user_id}
    }
    event = mock_stripe_event_factory(
        "customer.subscription.created", subscription_data, event_id=event_id
    )

    mock_db_subscription = AsyncMock(spec=DBSubscriptionModel)
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.db.get.return_value = mock_user # For resolving user_id if not in metadata

    await webhook_service.handle_customer_subscription_created(event)

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_db_subscription.status == "active"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    
    # Ensure no trial-specific logic was called
    webhook_service.db.add.assert_not_called() # No UsedTrialCardFingerprint, UserCredit, CreditTransaction added
    assert mock_user.has_consumed_initial_trial is False # Remains unchanged
    webhook_service.event_publisher.publish_user_trial_started.assert_not_called()
    webhook_service.db.commit.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
@patch("app.services.webhook_service.stripe.Subscription.delete") # For potential cancellation
async def test_handle_customer_subscription_created_trial_unique_fingerprint(
    mock_stripe_sub_delete: MagicMock,
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User # User has not consumed trial
):
    """Test trial subscription creation with a unique card fingerprint."""
    event_id = "evt_sub_trial_unique"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_trial_unique_123"
    stripe_price_id = "price_trial_123"
    card_fingerprint = "fp_trial_unique"
    default_pm_id = "pm_trial_unique"
    trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())

    subscription_data = {
        "id": stripe_subscription_id,
        "object": "subscription",
        "customer": stripe_customer_id,
        "status": "trialing",
        "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "trial_end": trial_end_ts,
        "default_payment_method": default_pm_id,
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": trial_end_ts,
        "cancel_at_period_end": False,
        "metadata": {"user_id": user_id}
    }
    event = mock_stripe_event_factory(
        "customer.subscription.created", subscription_data, event_id=event_id
    )

    mock_db_subscription = AsyncMock(spec=DBSubscriptionModel)
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.get.return_value = mock_user
    
    # Mock UserCredit query: first assume no UserCredit record exists
    mock_user_credit_select_result = AsyncMock()
    mock_user_credit_select_result.scalars.return_value.first.return_value = None
    
    # Mock User.id query (fallback if metadata user_id is missing)
    mock_user_id_select_result = AsyncMock()
    mock_user_id_select_result.scalars.return_value.first.return_value = user_id

    webhook_service.db.execute.side_effect = [
        mock_user_id_select_result, # For user_id lookup (if needed, though metadata has it)
        mock_user_credit_select_result # For UserCredit lookup
    ]


    # Mock event publisher
    webhook_service.event_publisher.publish_user_trial_started = AsyncMock()

    # Ensure flush does not raise IntegrityError for fingerprint
    webhook_service.db.flush = AsyncMock() 

    await webhook_service.handle_customer_subscription_created(event)

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    webhook_service.get_card_fingerprint_from_event.assert_called_once_with(event.data.object, event_id)
    
    # Check DB additions: UsedTrialCardFingerprint, UserCredit, CreditTransaction
    # We need to inspect the calls to db.add()
    assert webhook_service.db.add.call_count >= 3 # Fingerprint, UserCredit (if new), CreditTransaction
    
    added_objects = [call.args[0] for call in webhook_service.db.add.call_args_list]
    
    assert any(isinstance(obj, UsedTrialCardFingerprint) and obj.stripe_card_fingerprint == card_fingerprint for obj in added_objects)
    assert any(isinstance(obj, UserCredit) and obj.user_id == user_id for obj in added_objects) # Check if UserCredit was added or updated
    assert any(isinstance(obj, CreditTransaction) and obj.amount == 10 and obj.transaction_type == ModelTransactionType.TRIAL_CREDIT_GRANT for obj in added_objects)

    assert mock_user.has_consumed_initial_trial is True
    assert mock_user.account_status == "trialing"
    
    webhook_service.event_publisher.publish_user_trial_started.assert_called_once_with(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        trial_end_date=datetime.fromtimestamp(trial_end_ts, timezone.utc).isoformat(),
        credits_granted=10
    )
    mock_stripe_sub_delete.assert_not_called()
    webhook_service.db.commit.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
@patch("app.services.webhook_service.stripe.Subscription.delete")
async def test_handle_customer_subscription_created_trial_duplicate_fingerprint(
    mock_stripe_sub_delete: MagicMock,
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test trial subscription creation with a duplicate card fingerprint."""
    event_id = "evt_sub_trial_duplicate"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_trial_duplicate_123"
    card_fingerprint = "fp_trial_duplicate" # This fingerprint will cause IntegrityError

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_dup"}}]},
        "trial_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
        "default_payment_method": "pm_trial_dup", "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)

    mock_db_subscription = AsyncMock(spec=DBSubscriptionModel)
    mock_get_or_create_sub.return_value = mock_db_subscription
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.get.return_value = mock_user
    
    # Simulate IntegrityError when adding UsedTrialCardFingerprint
    webhook_service.db.flush = AsyncMock(side_effect=IntegrityError("uq_trial_card_fingerprint", params={}, orig=None))
    webhook_service.event_publisher.publish_user_trial_blocked = AsyncMock()

    await webhook_service.handle_customer_subscription_created(event)

    mock_get_or_create_sub.assert_called_once()
    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    
    # Check that UsedTrialCardFingerprint was attempted to be added
    assert any(isinstance(call.args[0], UsedTrialCardFingerprint) for call in webhook_service.db.add.call_args_list)
    
    mock_stripe_sub_delete.assert_called_once_with(stripe_subscription_id)
    assert mock_user.account_status == "trial_rejected"
    webhook_service.event_publisher.publish_user_trial_blocked.assert_called_once_with(
        user_id=user_id, stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id, reason="duplicate_card_fingerprint",
        blocked_card_fingerprint=card_fingerprint
    )
    webhook_service.db.commit.assert_called_once() # Commit for user status, subscription status update
    webhook_service.db.rollback.assert_called_once() # Rollback due to IntegrityError


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_trial_already_consumed(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test trial subscription when user has already consumed initial trial."""
    mock_user.has_consumed_initial_trial = True # User has consumed trial
    mock_user.account_status = "active" # Previous status
    original_balance = 5 # Assume some existing balance

    event_id = "evt_sub_trial_consumed"
    user_id = mock_user.id
    card_fingerprint = "fp_trial_consumed_unique" # Unique fingerprint this time

    subscription_data = {
        "id": "sub_trial_consumed_123", "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_cons"}}]},
        "trial_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
        "default_payment_method": "pm_trial_cons", "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)

    mock_db_subscription = AsyncMock(spec=DBSubscriptionModel)
    mock_get_or_create_sub.return_value = mock_db_subscription
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.get.return_value = mock_user
    
    # Mock UserCredit query: assume UserCredit record exists with some balance
    mock_user_credit_record = UserCredit(user_id=user_id, balance=original_balance, id="uc_123")
    mock_user_credit_select_result = AsyncMock()
    mock_user_credit_select_result.scalars.return_value.first.return_value = mock_user_credit_record
    webhook_service.db.execute.return_value = mock_user_credit_select_result # For UserCredit lookup

    webhook_service.db.flush = AsyncMock() # No IntegrityError for fingerprint

    await webhook_service.handle_customer_subscription_created(event)

    # Fingerprint should still be stored
    assert any(isinstance(call.args[0], UsedTrialCardFingerprint) for call in webhook_service.db.add.call_args_list)
    
    # No credits granted, no change to has_consumed_initial_trial
    assert not any(isinstance(call.args[0], CreditTransaction) for call in webhook_service.db.add.call_args_list)
    assert mock_user.has_consumed_initial_trial is True # Remains true
    
    # User account status might still go to 'trialing' if the subscription is 'trialing'
    # The service logic sets user.account_status = 'trialing' if not user.has_consumed_initial_trial
    # and then grants credits. If already consumed, it logs and does not grant credits.
    # The user.account_status update to 'trialing' happens *before* the credit grant check in the service.
    # This might be something to review in the service logic if a user who consumed a trial
    # starts *another* trial (e.g. different plan), should their status be 'trialing'?
    # For now, testing current behavior:
    # assert mock_user.account_status == "trialing" # This depends on service logic for already consumed trial

    webhook_service.event_publisher.publish_user_trial_started.assert_not_called()
    webhook_service.db.commit.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_missing_user_id(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test customer.subscription.created when user ID cannot be resolved."""
    event_id = "evt_sub_no_user"
    subscription_data = {
        "id": "sub_no_user_123", "object": "subscription", "customer": "cus_no_user_found",
        "status": "trialing", "items": {"data": [{"price": {"id": "price_no_user"}}]},
        "metadata": {} # No user_id in metadata
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)

    # Mock DB: User.id lookup returns None
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = None

    await webhook_service.handle_customer_subscription_created(event)

    mock_get_or_create_sub.assert_not_called() # Should return early
    webhook_service.db.commit.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_trial_missing_fingerprint(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test trial subscription creation when card fingerprint is missing."""
    event_id = "evt_sub_trial_no_fp"
    subscription_data = {
        "id": "sub_trial_no_fp_123", "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_no_fp"}}]},
        "trial_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
        "metadata": {"user_id": mock_user.id}
        # No default_payment_method or other source for fingerprint
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)

    mock_db_subscription = AsyncMock(spec=DBSubscriptionModel)
    mock_get_or_create_sub.return_value = mock_db_subscription
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=None) # Fingerprint is None
    webhook_service.db.get.return_value = mock_user

    with pytest.raises(ValueError, match="Card fingerprint missing for trial subscription"):
        await webhook_service.handle_customer_subscription_created(event)
    
    mock_get_or_create_sub.assert_called_once() # Subscription record update is attempted first
    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    webhook_service.db.commit.assert_not_called() # Should not commit due to error
    webhook_service.db.rollback.assert_not_called() # Rollback is handled by endpoint for raised exceptions
# Tests for WebhookService.handle_customer_subscription_updated
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # In case subscription is not found locally
async def test_handle_customer_subscription_updated_status_change_active_to_frozen(
    mock_get_or_create_sub: AsyncMock, # For fallback if sub not found
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test status transition from active to frozen (e.g., past_due)."""
    event_id = "evt_sub_updated_active_to_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_active_to_frozen_123"
    
    mock_user.account_status = "active" # Initial user status

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "past_due", # New Stripe status leading to 'frozen'
        "items": {"data": [{"price": {"id": "price_active_frozen"}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    # Mock existing DB subscription
    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    mock_db_sub.status = "active" # Old status
    mock_db_sub.stripe_subscription_id = stripe_subscription_id
    mock_db_sub.user_id = user_id
    
    # Mock DB calls:
    # 1. select Subscription
    # 2. get User
    mock_select_sub_result = AsyncMock()
    mock_select_sub_result.scalars.return_value.first.return_value = mock_db_sub
    webhook_service.db.execute.return_value = mock_select_sub_result
    webhook_service.db.get.return_value = mock_user
    
    webhook_service.event_publisher.publish_user_account_frozen = AsyncMock()

    await webhook_service.handle_customer_subscription_updated(event)

    webhook_service.db.execute.assert_called_once() # For select Subscription
    webhook_service.db.get.assert_called_once_with(User, user_id)
    
    assert mock_db_sub.status == "past_due" # Local subscription status updated
    assert mock_user.account_status == "frozen" # User status updated
    
    webhook_service.event_publisher.publish_user_account_frozen.assert_called_once_with(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        reason="subscription_status_change"
    )
    webhook_service.db.commit.assert_called_once()
    mock_get_or_create_sub.assert_not_called() # Should find existing sub

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_status_change_frozen_to_active(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test status transition from frozen to active."""
    event_id = "evt_sub_updated_frozen_to_active"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_frozen_to_active_123"

    mock_user.account_status = "frozen" # Initial user status

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "active", # New Stripe status
        "items": {"data": [{"price": {"id": "price_frozen_active"}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    mock_db_sub.status = "past_due" # Old status
    mock_db_sub.stripe_subscription_id = stripe_subscription_id
    mock_db_sub.user_id = user_id

    mock_select_sub_result = AsyncMock()
    mock_select_sub_result.scalars.return_value.first.return_value = mock_db_sub
    webhook_service.db.execute.return_value = mock_select_sub_result
    webhook_service.db.get.return_value = mock_user
    
    webhook_service.event_publisher.publish_user_account_unfrozen = AsyncMock()

    await webhook_service.handle_customer_subscription_updated(event)

    assert mock_db_sub.status == "active"
    assert mock_user.account_status == "active"
    
    webhook_service.event_publisher.publish_user_account_unfrozen.assert_called_once_with(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        reason="subscription_status_change"
    )
    webhook_service.db.commit.assert_called_once()
    mock_get_or_create_sub.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_local_sub_not_found(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test handling when local subscription record doesn't exist initially."""
    event_id = "evt_sub_updated_sub_not_found"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_not_found_123"

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "active", "items": {"data": [{"price": {"id": "price_sub_not_found"}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    # Mock DB: select Subscription returns None
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = None
    
    # Mock get_or_create_subscription to return a new mock subscription
    new_mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    new_mock_db_sub.stripe_customer_id = None # Simulate it being newly created
    mock_get_or_create_sub.return_value = new_mock_db_sub
    
    webhook_service.db.get.return_value = mock_user # User is found

    await webhook_service.handle_customer_subscription_updated(event)

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert new_mock_db_sub.status == "active"
    assert new_mock_db_sub.stripe_customer_id == stripe_customer_id # Ensure it's set
    assert mock_user.account_status == "active" # Assuming user was not 'active' or status changed
    webhook_service.db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_handle_customer_subscription_updated_missing_user_id(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test customer.subscription.updated when user ID cannot be resolved."""
    event_id = "evt_sub_updated_no_user"
    subscription_data = {
        "id": "sub_updated_no_user_123", "object": "subscription", "customer": "cus_updated_no_user",
        "status": "active", "items": {"data": [{"price": {"id": "price_updated_no_user"}}]},
        "metadata": {} # No user_id
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    # Mock DB: User.id lookup returns None
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = None # For user_id from stripe_customer_id

    await webhook_service.handle_customer_subscription_updated(event)
    
    # First execute is for user_id from stripe_customer_id
    webhook_service.db.execute.assert_called_once() 
    webhook_service.db.get.assert_not_called() # Not called if user_id not found
    webhook_service.db.commit.assert_not_called()
# Tests for WebhookService.handle_invoice_payment_succeeded
@pytest.mark.asyncio
async def test_handle_invoice_payment_succeeded_success_active_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User # User is already active
):
    """Test invoice.payment_succeeded for an already active user."""
    event_id = "evt_inv_paid_active"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_inv_paid_active_123"
    stripe_invoice_id = "in_inv_paid_active_123"

    mock_user.account_status = "active" # Ensure initial state

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id,
        "status": "paid",
        "amount_paid": 1000, "currency": "usd", "billing_reason": "subscription_cycle",
        "invoice_pdf": "https://example.com/invoice.pdf",
        "customer_details": {"metadata": {"user_id": user_id}} # Assume user_id in customer metadata
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

    # Mock DB: User found
    webhook_service.db.get.return_value = mock_user
    
    # Mock DB: Subscription found and is active
    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    mock_db_sub.status = "active"
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = mock_db_sub

    webhook_service.event_publisher.publish_user_invoice_paid = AsyncMock()
    webhook_service.event_publisher.publish_user_account_unfrozen = AsyncMock()

    await webhook_service.handle_invoice_payment_succeeded(event)

    webhook_service.db.get.assert_called_once_with(User, user_id)
    webhook_service.db.execute.assert_called_once() # For subscription select

    assert mock_user.account_status == "active" # Remains active
    assert mock_db_sub.status == "active" # Remains active
    
    webhook_service.event_publisher.publish_user_invoice_paid.assert_called_once()
    # Check specific args if needed
    call_args = webhook_service.event_publisher.publish_user_invoice_paid.call_args[1]
    assert call_args['user_id'] == user_id
    assert call_args['stripe_invoice_id'] == stripe_invoice_id
    assert call_args['amount_paid'] == 1000

    webhook_service.event_publisher.publish_user_account_unfrozen.assert_not_called()
    webhook_service.db.commit.assert_called_once() # Commit might happen even if status doesn't change, depending on merge logic

@pytest.mark.asyncio
async def test_handle_invoice_payment_succeeded_unfreezes_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test invoice.payment_succeeded unfreezes a frozen user."""
    event_id = "evt_inv_paid_unfreeze"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_inv_paid_unfreeze_123"
    stripe_invoice_id = "in_inv_paid_unfreeze_123"

    mock_user.account_status = "frozen" # Initial state

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "paid",
        "amount_paid": 1000, "currency": "usd", "billing_reason": "subscription_cycle",
        "invoice_pdf": "https://example.com/invoice.pdf",
        "customer_details": {"metadata": {"user_id": user_id}}
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

    webhook_service.db.get.return_value = mock_user
    
    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    mock_db_sub.status = "past_due" # Subscription was past_due
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = mock_db_sub

    webhook_service.event_publisher.publish_user_invoice_paid = AsyncMock()
    webhook_service.event_publisher.publish_user_account_unfrozen = AsyncMock()

    await webhook_service.handle_invoice_payment_succeeded(event)

    webhook_service.db.get.assert_called_once_with(User, user_id)
    webhook_service.db.execute.assert_called_once() # For subscription select

    assert mock_user.account_status == "active" # Status updated
    assert mock_db_sub.status == "active" # Subscription status updated
    
    webhook_service.event_publisher.publish_user_invoice_paid.assert_called_once()
    webhook_service.event_publisher.publish_user_account_unfrozen.assert_called_once_with(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        reason="invoice_paid_after_failure"
    )
    webhook_service.db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_handle_invoice_payment_succeeded_missing_user_id(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test invoice.payment_succeeded when user ID cannot be resolved."""
    event_id = "evt_inv_paid_no_user"
    invoice_data = {
        "id": "in_inv_paid_no_user_123", "object": "invoice", "customer": "cus_inv_paid_no_user",
        "subscription": "sub_inv_paid_no_user_123", "status": "paid",
        "customer_details": {"metadata": {}} # No user_id in metadata
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

    # Mock DB: User.id lookup returns None
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = None

    await webhook_service.handle_invoice_payment_succeeded(event)

    webhook_service.db.execute.assert_called_once() # Attempted user lookup via stripe_customer_id
    webhook_service.db.get.assert_not_called()
    webhook_service.db.commit.assert_not_called()
    webhook_service.event_publisher.publish_user_invoice_paid.assert_not_called()
    webhook_service.event_publisher.publish_user_account_unfrozen.assert_not_called()

@pytest.mark.asyncio
async def test_handle_invoice_payment_succeeded_user_not_found_in_db(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test invoice.payment_succeeded when user exists in Stripe metadata but not DB."""
    event_id = "evt_inv_paid_user_not_db"
    user_id = "non_existent_user_id"
    invoice_data = {
        "id": "in_inv_paid_user_not_db_123", "object": "invoice", "customer": "cus_inv_paid_user_not_db",
        "subscription": "sub_inv_paid_user_not_db_123", "status": "paid",
        "customer_details": {"metadata": {"user_id": user_id}} # User ID present
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

    # Mock DB: User lookup returns None
    webhook_service.db.get.return_value = None

    await webhook_service.handle_invoice_payment_succeeded(event)

    webhook_service.db.get.assert_called_once_with(User, user_id)
    webhook_service.db.execute.assert_not_called() # No subscription lookup if user not found
    webhook_service.db.commit.assert_not_called()
    # Patch publisher methods for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_paid, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_unfrozen:
        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_paid.assert_not_called()
        mock_unfrozen.assert_not_called()
# Tests for WebhookService.handle_invoice_payment_failed
@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_freezes_active_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User # User is initially active
):
    """Test invoice.payment_failed freezes an active user for subscription invoice."""
    event_id = "evt_inv_failed_freeze"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_inv_failed_freeze_123"
    stripe_invoice_id = "in_inv_failed_freeze_123"
    
    mock_user.account_status = "active" # Initial state

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, # Related to subscription
        "status": "open", # Or "void", "uncollectible" - status indicates failure
        "billing_reason": "subscription_cycle", # Reason indicates it should freeze
        "amount_paid": 0, "currency": "usd", 
        "last_payment_error": {"message": "Card declined"},
        "next_payment_attempt": int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp()),
        "customer_details": {"metadata": {"user_id": user_id}}
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    # Mock DB: User found
    webhook_service.db.get.return_value = mock_user
    
    # Mock DB: Subscription found (needed for the check)
    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = mock_db_sub

    webhook_service.event_publisher.publish_user_invoice_failed = AsyncMock()
    webhook_service.event_publisher.publish_user_account_frozen = AsyncMock()

    await webhook_service.handle_invoice_payment_failed(event)

    webhook_service.db.get.assert_called_once_with(User, user_id)
    webhook_service.db.execute.assert_called_once() # For subscription select

    assert mock_user.account_status == "frozen" # Status updated
    
    webhook_service.event_publisher.publish_user_invoice_failed.assert_called_once()
    # Check specific args if needed
    fail_call_args = webhook_service.event_publisher.publish_user_invoice_failed.call_args[1]
    assert fail_call_args['user_id'] == user_id
    assert fail_call_args['stripe_invoice_id'] == stripe_invoice_id
    assert fail_call_args['failure_reason'] == "Card declined"

    webhook_service.event_publisher.publish_user_account_frozen.assert_called_once_with(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        reason="invoice_payment_failed"
    )
    webhook_service.db.commit.assert_called_once() # Commit because status changed

@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_already_frozen_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test invoice.payment_failed for an already frozen user."""
    event_id = "evt_inv_failed_already_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_inv_failed_frozen_123"
    stripe_invoice_id = "in_inv_failed_frozen_123"
    
    mock_user.account_status = "frozen" # Initial state

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "open",
        "billing_reason": "subscription_cycle",
        "last_payment_error": {"message": "Insufficient funds"},
        "customer_details": {"metadata": {"user_id": user_id}}
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    webhook_service.db.get.return_value = mock_user
    mock_db_sub = AsyncMock(spec=DBSubscriptionModel)
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = mock_db_sub
    webhook_service.event_publisher.publish_user_invoice_failed = AsyncMock()
    webhook_service.event_publisher.publish_user_account_frozen = AsyncMock()

    await webhook_service.handle_invoice_payment_failed(event)

    assert mock_user.account_status == "frozen" # Remains frozen
    
    webhook_service.event_publisher.publish_user_invoice_failed.assert_called_once()
    webhook_service.event_publisher.publish_user_account_frozen.assert_not_called() # Not called again
    webhook_service.db.commit.assert_not_called() # No status change, so no commit needed

@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_non_subscription_reason(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    """Test invoice.payment_failed for non-subscription reason doesn't freeze."""
    event_id = "evt_inv_failed_non_sub"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_invoice_id = "in_inv_failed_non_sub_123"
    
    mock_user.account_status = "active" # Initial state

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": None, # Not related to a subscription
        "status": "open",
        "billing_reason": "manual", # Manual invoice, not subscription cycle
        "last_payment_error": {"message": "Card declined"},
        "customer_details": {"metadata": {"user_id": user_id}}
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    webhook_service.db.get.return_value = mock_user
    webhook_service.event_publisher.publish_user_invoice_failed = AsyncMock()
    webhook_service.event_publisher.publish_user_account_frozen = AsyncMock()

    await webhook_service.handle_invoice_payment_failed(event)

    assert mock_user.account_status == "active" # Remains active
    
    webhook_service.event_publisher.publish_user_invoice_failed.assert_called_once()
    webhook_service.event_publisher.publish_user_account_frozen.assert_not_called()
    webhook_service.db.commit.assert_not_called() # No status change

@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_missing_user_id(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test invoice.payment_failed when user ID cannot be resolved."""
    event_id = "evt_inv_failed_no_user"
    invoice_data = {
        "id": "in_inv_failed_no_user_123", "object": "invoice", "customer": "cus_inv_failed_no_user",
        "subscription": "sub_inv_failed_no_user_123", "status": "open",
        "billing_reason": "subscription_cycle",
        "customer_details": {"metadata": {}} # No user_id
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    # Mock DB: User.id lookup returns None
    webhook_service.db.execute.return_value.scalars.return_value.first.return_value = None

    await webhook_service.handle_invoice_payment_failed(event)

    webhook_service.db.execute.assert_called_once() # Attempted user lookup
    webhook_service.db.get.assert_not_called()
    webhook_service.db.commit.assert_not_called()
    webhook_service.event_publisher.publish_user_invoice_failed.assert_not_called()
    webhook_service.event_publisher.publish_user_account_frozen.assert_not_called()

@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_user_not_found_in_db(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    """Test invoice.payment_failed when user exists in Stripe metadata but not DB."""
    event_id = "evt_inv_failed_user_not_db"
    user_id = "non_existent_user_id"
    invoice_data = {
        "id": "in_inv_failed_user_not_db_123", "object": "invoice", "customer": "cus_inv_failed_user_not_db",
        "subscription": "sub_inv_failed_user_not_db_123", "status": "open",
        "billing_reason": "subscription_cycle",
        "customer_details": {"metadata": {"user_id": user_id}} # User ID present
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    # Mock DB: User lookup returns None
    webhook_service.db.get.return_value = None

    await webhook_service.handle_invoice_payment_failed(event)

    webhook_service.db.get.assert_called_once_with(User, user_id)
    webhook_service.db.execute.assert_not_called() # No subscription lookup if user not found
    webhook_service.db.commit.assert_not_called()
    # Patch publisher methods for this test
    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_failed.assert_not_called()
        mock_frozen.assert_not_called()
# Integration Tests for the /webhooks/stripe endpoint
# These tests use the TestClient to simulate HTTP requests

# Helper to simulate the dependency override for verify_stripe_signature
def create_mock_verify_dependency(mock_event: stripe.Event) -> Callable:
    async def mock_verify_stripe_signature_override(
        request: Request,
        stripe_signature: str = Header(None)
    ):
        # Basic check for header presence, actual verification is bypassed
        if not stripe_signature:
             raise HTTPException(status_code=400, detail="Stripe-Signature header missing.")
        # Return the pre-constructed mock event
        return mock_event
    return mock_verify_stripe_signature_override

@pytest.mark.asyncio
@patch("app.services.webhook_service.WebhookService.is_event_processed", return_value=False)
@patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", new_callable=AsyncMock)
@patch("app.services.webhook_service.WebhookService.mark_event_as_processed", new_callable=AsyncMock)
async def test_stripe_webhook_endpoint_checkout_session_completed(
    mock_mark_processed: AsyncMock,
    mock_handle_checkout: AsyncMock,
    mock_is_processed: AsyncMock,
    client: AsyncClient, # Use the test client fixture
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock # Need this for the get_db override
):
    """Integration test for a valid checkout.session.completed event."""
    event_type = "checkout.session.completed"
    event_id = "evt_integ_checkout_success"
    payload_data = {"id": "cs_integ_test", "customer": "cus_integ_test"}
    mock_event = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    # Override dependencies: get_db and verify_stripe_signature
    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
    main_app.dependency_overrides[WebhookService] = lambda: WebhookService(mock_db_session) # Ensure mocked service is used

    # Simulate the POST request
    response = await client.post(
        "/webhooks/stripe",
        content=b'{"some": "payload"}', # Payload content doesn't matter much as verify is mocked
        headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Webhook received and processed"}

    # Verify mocks
    mock_is_processed.assert_called_once_with(event_id)
    mock_handle_checkout.assert_called_once_with(mock_event)
    mock_mark_processed.assert_called_once_with(event_id, event_type)

    # Clean up overrides
    main_app.dependency_overrides = {}


@pytest.mark.asyncio
@patch("app.services.webhook_service.WebhookService.is_event_processed", return_value=True) # Event IS processed
@patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", new_callable=AsyncMock)
@patch("app.services.webhook_service.WebhookService.mark_event_as_processed", new_callable=AsyncMock)
async def test_stripe_webhook_endpoint_idempotency(
    mock_mark_processed: AsyncMock,
    mock_handle_checkout: AsyncMock,
    mock_is_processed: AsyncMock,
    client: AsyncClient,
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock
):
    """Integration test for idempotency - event already processed."""
    event_type = "checkout.session.completed"
    event_id = "evt_integ_already_processed"
    payload_data = {"id": "cs_integ_idem_test"}
    mock_event = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
    main_app.dependency_overrides[WebhookService] = lambda: WebhookService(mock_db_session)

    response = await client.post(
        "/webhooks/stripe",
        content=b'{}',
        headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Event already processed"}

    mock_is_processed.assert_called_once_with(event_id)
    mock_handle_checkout.assert_not_called() # Handler should not be called
    mock_mark_processed.assert_not_called() # Should not be marked again

    main_app.dependency_overrides = {}


@pytest.mark.asyncio
@patch("app.services.webhook_service.WebhookService.is_event_processed", return_value=False)
@patch("app.services.webhook_service.WebhookService.mark_event_as_processed", new_callable=AsyncMock)
# Patch specific handlers to ensure they are NOT called for unhandled type
@patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", new_callable=AsyncMock)
@patch("app.services.webhook_service.WebhookService.handle_customer_subscription_created", new_callable=AsyncMock)
# Add patches for other handlers if needed...
async def test_stripe_webhook_endpoint_unhandled_event_type(
    mock_handle_sub_created: AsyncMock,
    mock_handle_checkout: AsyncMock,
    mock_mark_processed: AsyncMock,
    mock_is_processed: AsyncMock,
    client: AsyncClient,
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock
):
    """Integration test for an unhandled event type."""
    event_type = "some.other.event" # An event type not explicitly handled
    event_id = "evt_integ_unhandled"
    payload_data = {"id": "obj_integ_unhandled"}
    mock_event = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
    main_app.dependency_overrides[WebhookService] = lambda: WebhookService(mock_db_session)

    response = await client.post(
        "/webhooks/stripe",
        content=b'{}',
        headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": f"Webhook received for unhandled event type: {event_type}"}

    mock_is_processed.assert_called_once_with(event_id)
    mock_handle_checkout.assert_not_called() # Ensure specific handlers were not called
    mock_handle_sub_created.assert_not_called()
    mock_mark_processed.assert_called_once_with(event_id, event_type) # Should still be marked processed

    main_app.dependency_overrides = {}


@pytest.mark.asyncio
@patch("app.services.webhook_service.WebhookService.is_event_processed", return_value=False)
@patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", new_callable=AsyncMock, side_effect=Exception("Handler error!"))
@patch("app.services.webhook_service.WebhookService.mark_event_as_processed", new_callable=AsyncMock)
async def test_stripe_webhook_endpoint_handler_exception(
    mock_mark_processed: AsyncMock,
    mock_handle_checkout: AsyncMock,
    mock_is_processed: AsyncMock,
    client: AsyncClient,
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock
):
    """Integration test for an exception occurring within an event handler."""
    event_type = "checkout.session.completed"
    event_id = "evt_integ_handler_error"
    payload_data = {"id": "cs_integ_handler_error"}
    mock_event = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
    main_app.dependency_overrides[WebhookService] = lambda: WebhookService(mock_db_session)

    response = await client.post(
        "/webhooks/stripe",
        content=b'{}',
        headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
    )

    assert response.status_code == 500 # Expecting 500 due to handler error
    assert response.json() == {"detail": "Internal server error processing webhook."}

    mock_is_processed.assert_called_once_with(event_id)
    mock_handle_checkout.assert_called_once_with(mock_event)
    mock_mark_processed.assert_not_called() # Should NOT be marked processed on error

    main_app.dependency_overrides = {}
# More tests will be added below for each checklist item.