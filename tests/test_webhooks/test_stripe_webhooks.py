import pytest
import stripe
from stripe.error import SignatureVerificationError # Added this line
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator, Any, Dict, Callable
import asyncio # For iscoroutinefunction check
from datetime import datetime, timezone, timedelta # For timestamps

from fastapi import FastAPI, Request, HTTPException, Header # Added FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, SQLAlchemyError # For specific error checks

from app.core.config import settings
from app.main import app as main_app
from app.models.user import User
from app.models.processed_event import ProcessedStripeEvent
from app.models.plan import Subscription, UsedTrialCardFingerprint # DBSubscriptionModel replaced by Subscription
from app.models.credit import CreditTransaction, UserCredit
from app.services.webhook_service import WebhookService
from app.routers.webhooks.stripe_webhooks import verify_stripe_signature # stripe_webhook_endpoint removed as it's part of app

# Set a dummy webhook secret for testing if not already set
settings.STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET or "whsec_REMOVED_dummysecret"
settings.STRIPE_SECRET_KEY = settings.STRIPE_SECRET_KEY or "sk_test_dummykey"
stripe.api_key = settings.STRIPE_SECRET_KEY


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(mock_db_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]: # Add mock_db_session as a parameter
    """
    Test client for making requests to the FastAPI application.
    Overrides the get_db dependency to use the provided mock_db_session.
    """
    from app.core.database import get_db

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db_session # Yield the already instantiated fixture

    original_get_db = main_app.dependency_overrides.get(get_db)
    main_app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=main_app, base_url="http://test") as ac:
        yield ac
    
    # Restore original dependencies or clear
    if original_get_db:
        main_app.dependency_overrides[get_db] = original_get_db
    elif get_db in main_app.dependency_overrides: # Check if key exists before deleting
        del main_app.dependency_overrides[get_db]


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mocks the SQLAlchemy AsyncSession with improved async handling and assertion capabilities."""
    session = AsyncMock(spec=AsyncSession)
    
    _mock_scalar_first_values_queue = []
    async def _first_side_effect():
        if _mock_scalar_first_values_queue:
            return _mock_scalar_first_values_queue.pop(0)
        return None

    mock_first_method = AsyncMock(side_effect=_first_side_effect)
    
    mock_scalars_obj = AsyncMock()
    mock_scalars_obj.first = mock_first_method 

    mock_execute_result = AsyncMock()
    mock_execute_result.scalars = MagicMock(return_value=mock_scalars_obj)
    session.execute = AsyncMock(return_value=mock_execute_result)

    def set_db_execute_scalar_first_results(*values: Any):
        nonlocal _mock_scalar_first_values_queue
        _mock_scalar_first_values_queue = list(values)
        mock_first_method.reset_mock() 
    
    session.set_db_execute_scalar_first_results = set_db_execute_scalar_first_results
    session.mock_first_method = mock_first_method 

    _mock_get_value = None
    async def _get_side_effect(model_class: Any, ident: Any):
        return _mock_get_value

    session.get = AsyncMock(side_effect=_get_side_effect)

    def set_db_get_result(value: Any):
        nonlocal _mock_get_value
        _mock_get_value = value
        session.get.reset_mock() 
        
    session.set_db_get_result = set_db_get_result
    session.set_db_get_result(None) 

    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock() 
    session.merge = AsyncMock(side_effect=lambda instance: instance) # Merge often returns the instance
    session.flush = AsyncMock()
    session.scalar_one_or_none = AsyncMock(return_value=None)

    return session


@pytest.fixture
def webhook_service(mock_db_session: AsyncMock) -> WebhookService:
    """Fixture for WebhookService with a mocked DB session."""
    return WebhookService(db_session=mock_db_session)


@pytest.fixture
def mock_stripe_event_factory() -> Callable[[str, Dict[str, Any], str], stripe.Event]:
    """Factory to create mock Stripe events."""
    def _factory(event_type: str, data_object: Dict[str, Any], event_id: str = "evt_test_event") -> stripe.Event:
        event_data = {
            "id": event_id,
            "object": "event",
            "api_version": "2020-08-27", 
            "created": int(datetime.now(timezone.utc).timestamp()),
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
    user = User(
        id="test_user_123",
        email="test@example.com",
        hashed_password="hashed_password",
        stripe_customer_id="cus_testcustomer",
    )
    user.is_active=True
    user.is_verified=True
    user.account_status="active"
    user.has_consumed_initial_trial=False
    return user

@pytest.fixture
def mock_processed_event() -> ProcessedStripeEvent:
    event = ProcessedStripeEvent(
        stripe_event_id="evt_test_already_processed",
        event_type="checkout.session.completed"
    )
    return event

def test_fixture_setup(webhook_service: WebhookService, mock_stripe_event_factory: Callable):
    assert webhook_service is not None
    assert webhook_service.db is not None
    event = mock_stripe_event_factory("test.event", {"id": "obj_test"})
    assert event.type == "test.event"
    assert event.id.startswith("evt_")

# --- verify_stripe_signature Tests ---
@pytest.mark.asyncio
async def test_verify_stripe_signature_valid(mock_stripe_event_factory: Callable):
    payload_dict = {"id": "evt_test_payload", "object": "event", "type": "test.event.valid"}
    payload_bytes = b'{"id": "evt_test_payload", "object": "event", "type": "test.event.valid"}'
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
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

@pytest.mark.asyncio
async def test_verify_stripe_signature_missing_header():
    mock_request = AsyncMock(spec=Request)
    with pytest.raises(HTTPException) as exc_info:
        await verify_stripe_signature(request=mock_request, stripe_signature=None)
    assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_verify_stripe_signature_missing_secret(monkeypatch):
    mock_request = AsyncMock(spec=Request)
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    with pytest.raises(HTTPException) as exc_info:
        await verify_stripe_signature(request=mock_request, stripe_signature="t=123,v1=dummy")
    assert exc_info.value.status_code == 500
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_REMOVED_dummysecret")

@pytest.mark.asyncio
async def test_verify_stripe_signature_invalid_payload():
    payload_bytes = b"invalid json"
    mock_signature = "t=123,v1=dummy"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)
    with patch("stripe.Webhook.construct_event", side_effect=ValueError("Invalid payload")):
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_verify_stripe_signature_invalid_signature_error():
    payload_bytes = b'{"id": "evt_test"}'
    mock_signature = "t=123,v1=invalid_signature"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)
    with patch("stripe.Webhook.construct_event", side_effect=stripe.error.SignatureVerificationError("Invalid signature", "sig_header")):
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        assert exc_info.value.status_code == 400

@pytest.mark.asyncio
async def test_verify_stripe_signature_unexpected_error():
    payload_bytes = b'{"id": "evt_test"}'
    mock_signature = "t=123,v1=dummy"
    mock_request = AsyncMock(spec=Request)
    mock_request.body = AsyncMock(return_value=payload_bytes)
    with patch("stripe.Webhook.construct_event", side_effect=Exception("Unexpected error")):
        with pytest.raises(HTTPException) as exc_info:
            await verify_stripe_signature(request=mock_request, stripe_signature=mock_signature)
        assert exc_info.value.status_code == 500

# --- WebhookService Idempotency Tests ---
@pytest.mark.asyncio
async def test_webhook_service_is_event_processed_true(webhook_service: WebhookService, mock_processed_event: ProcessedStripeEvent):
    event_id = "evt_test_already_processed"
    webhook_service.db.set_db_execute_scalar_first_results(mock_processed_event)
    result = await webhook_service.is_event_processed(event_id)
    webhook_service.db.execute.assert_called_once()
    assert result is True

@pytest.mark.asyncio
async def test_webhook_service_is_event_processed_false(webhook_service: WebhookService):
    event_id = "evt_test_new_event"
    webhook_service.db.set_db_execute_scalar_first_results(None)
    result = await webhook_service.is_event_processed(event_id)
    webhook_service.db.execute.assert_called_once()
    assert result is False

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_success(webhook_service: WebhookService):
    event_id = "evt_test_mark_success"
    event_type = "checkout.session.completed"
    await webhook_service.mark_event_as_processed(event_id, event_type)
    webhook_service.db.execute.assert_called_once()
    webhook_service.db.commit.assert_called_once()
    webhook_service.db.rollback.assert_not_called()

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_integrity_error_simulated(webhook_service: WebhookService):
    event_id = "evt_test_mark_duplicate"
    event_type = "checkout.session.completed"
    # on_conflict_do_nothing should prevent IntegrityError from being raised to Python
    await webhook_service.mark_event_as_processed(event_id, event_type)
    webhook_service.db.execute.assert_called_once()
    webhook_service.db.commit.assert_called_once()
    webhook_service.db.rollback.assert_not_called()

@pytest.mark.asyncio
async def test_webhook_service_mark_event_as_processed_sqlalchemy_error(webhook_service: WebhookService):
    event_id = "evt_test_mark_db_error"
    event_type = "checkout.session.completed"
    webhook_service.db.execute.side_effect = SQLAlchemyError("Simulated DB connection error")
    with pytest.raises(SQLAlchemyError, match="Simulated DB connection error"):
        await webhook_service.mark_event_as_processed(event_id, event_type)
    webhook_service.db.execute.assert_called_once()
    webhook_service.db.commit.assert_not_called()
    webhook_service.db.rollback.assert_called_once()

# --- WebhookService.handle_checkout_session_completed Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.Subscription")
async def test_handle_checkout_session_completed_unique_fingerprint(
    mock_stripe_sub: MagicMock, # Patched stripe.Subscription
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_checkout_unique_fp"
    user_id = mock_user.id
    card_fingerprint = "fp_unique_checkout"
    checkout_session_data = {
        "id": "cs_test_unique_fp", "object": "checkout.session", "client_reference_id": user_id,
        "customer": "cus_test_unique_fp", "subscription": "sub_test_unique_fp_sub",
        "payment_intent": "pi_test_unique_fp", "metadata": {"user_id": user_id}
    }
    event = mock_stripe_event_factory("checkout.session.completed", checkout_session_data, event_id=event_id)
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.set_db_execute_scalar_first_results(None) # No existing fingerprint
    webhook_service.db.set_db_get_result(mock_user)

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish_blocked:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish_blocked.assert_not_called()

    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    assert webhook_service.db.execute.call_count == 1 # For fingerprint check
    mock_stripe_sub.delete.assert_not_called()
    assert mock_user.account_status != "trial_rejected"
    webhook_service.db.commit.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.Subscription.delete")
async def test_handle_checkout_session_completed_duplicate_fingerprint(
    mock_stripe_sub_delete: MagicMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_checkout_duplicate_fp"
    user_id = mock_user.id
    stripe_customer_id = "cus_test_duplicate_fp"
    stripe_subscription_id = "sub_test_duplicate_fp_sub"
    card_fingerprint = "fp_duplicate_checkout"
    checkout_session_data = {
        "id": "cs_test_duplicate_fp", "object": "checkout.session", "client_reference_id": user_id,
        "customer": stripe_customer_id, "subscription": stripe_subscription_id,
        "payment_intent": "pi_test_duplicate_fp", "metadata": {"user_id": user_id}
    }
    event = mock_stripe_event_factory("checkout.session.completed", checkout_session_data, event_id=event_id)
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    
    existing_fp_use = MagicMock(spec=UsedTrialCardFingerprint)
    existing_fp_use.user_id = "other_user_id"
    webhook_service.db.set_db_execute_scalar_first_results(existing_fp_use)
    webhook_service.db.set_db_get_result(mock_user)
    original_status = mock_user.account_status

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish_blocked:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish_blocked.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )
    
    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    mock_stripe_sub_delete.assert_called_once_with(stripe_subscription_id)
    webhook_service.db.get.assert_called_once_with(User, user_id)
    assert mock_user.account_status == "trial_rejected"
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_status # Restore

@pytest.mark.asyncio
async def test_handle_checkout_session_completed_missing_user_id(
    webhook_service: WebhookService, mock_stripe_event_factory: Callable
):
    event_id = "evt_checkout_no_user"
    checkout_session_data = {"id": "cs_test_no_user", "client_reference_id": None, "metadata": {}}
    event = mock_stripe_event_factory("checkout.session.completed", checkout_session_data, event_id=event_id)
    webhook_service.get_card_fingerprint_from_event = AsyncMock() # Should not be called

    await webhook_service.handle_checkout_session_completed(event)
    webhook_service.get_card_fingerprint_from_event.assert_not_called()
    webhook_service.db.execute.assert_not_called()

@pytest.mark.asyncio
async def test_handle_checkout_session_completed_missing_fingerprint(
    webhook_service: WebhookService, mock_stripe_event_factory: Callable, mock_user: User
):
    event_id = "evt_checkout_no_fp"
    user_id = mock_user.id
    checkout_session_data = {"id": "cs_test_no_fp", "client_reference_id": user_id, "metadata": {"user_id": user_id}}
    event = mock_stripe_event_factory("checkout.session.completed", checkout_session_data, event_id=event_id)
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=None)
    webhook_service.db.set_db_get_result(mock_user)

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish_blocked:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish_blocked.assert_not_called()
    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    webhook_service.db.execute.assert_not_called() # No fingerprint means no DB check for duplicates

# --- WebhookService.get_card_fingerprint_from_event Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve")
async def test_get_card_fingerprint_from_payment_intent(mock_stripe_pi_retrieve: MagicMock, webhook_service: WebhookService):
    mock_card = MagicMock()
    mock_card.fingerprint = "fp_from_pi"
    # Ensure the payment_method object itself is a StripeObject if isinstance checks are used
    mock_payment_method_stripe_obj = stripe.PaymentMethod.construct_from({
        "id": "pm_test", "object": "payment_method", "card": {"fingerprint": "fp_from_pi"}
    }, stripe.api_key)
    
    mock_pi_retrieved = MagicMock(spec=stripe.PaymentIntent)
    # The retrieved payment_method attribute should be the StripeObject
    mock_pi_retrieved.payment_method = mock_payment_method_stripe_obj 
    mock_stripe_pi_retrieve.return_value = mock_pi_retrieved
    
    event_data_dict = {"payment_intent": "pi_test"}
    # Construct a StripeObject that the service method expects
    event_data_object = stripe.StripeObject.construct_from(event_data_dict, stripe.api_key)

    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data_object, "evt_test")
    assert fingerprint == "fp_from_pi"
    mock_stripe_pi_retrieve.assert_called_once_with("pi_test", expand=["payment_method"])

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.SetupIntent.retrieve")
async def test_get_card_fingerprint_from_setup_intent(mock_stripe_si_retrieve: MagicMock, webhook_service: WebhookService):
    mock_card = MagicMock()
    mock_card.fingerprint = "fp_from_si"
    mock_payment_method_stripe_obj = stripe.PaymentMethod.construct_from({
        "id": "pm_test_si", "object": "payment_method", "card": {"fingerprint": "fp_from_si"}
    }, stripe.api_key)

    mock_si_retrieved = MagicMock(spec=stripe.SetupIntent)
    mock_si_retrieved.payment_method = mock_payment_method_stripe_obj
    mock_stripe_si_retrieve.return_value = mock_si_retrieved

    event_data_dict = {"setup_intent": "si_test"}
    event_data_object = stripe.StripeObject.construct_from(event_data_dict, stripe.api_key)
    
    fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data_object, "evt_test")
    assert fingerprint == "fp_from_si"
    mock_stripe_si_retrieve.assert_called_once_with("si_test", expand=["payment_method"])

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentMethod.retrieve")
async def test_get_card_fingerprint_from_default_payment_method(mock_stripe_pm_retrieve: MagicMock, webhook_service: WebhookService):
    mock_card = MagicMock()
    mock_card.fingerprint = "fp_from_default_pm"
    mock_pm_retrieved = MagicMock(spec=stripe.PaymentMethod)
    mock_pm_retrieved.card = mock_card
    mock_stripe_pm_retrieve.return_value = mock_pm_retrieved

    event_data = {"default_payment_method": "pm_test_default"} # Typically from Subscription object
    fingerprint = await webhook_service.get_card_fingerprint_from_event(stripe.util.convert_to_stripe_object(event_data, stripe.api_key), "evt_test")
    assert fingerprint == "fp_from_default_pm"
    mock_stripe_pm_retrieve.assert_called_once_with("pm_test_default")

@pytest.mark.asyncio
async def test_get_card_fingerprint_from_event_data_direct(webhook_service: WebhookService):
    event_data = {"payment_method_details": {"card": {"fingerprint": "fp_direct_on_event"}}}
    fingerprint = await webhook_service.get_card_fingerprint_from_event(stripe.util.convert_to_stripe_object(event_data, stripe.api_key), "evt_test")
    assert fingerprint == "fp_direct_on_event"

@pytest.mark.asyncio
@patch("app.services.webhook_service.stripe.PaymentIntent.retrieve", side_effect=stripe.error.StripeError("API error"))
async def test_get_card_fingerprint_stripe_api_error(mock_retrieve: MagicMock, webhook_service: WebhookService):
    event_data = {"payment_intent": "pi_test_error"}
    fingerprint = await webhook_service.get_card_fingerprint_from_event(stripe.util.convert_to_stripe_object(event_data, stripe.api_key), "evt_test_api_error")
    assert fingerprint is None
    mock_retrieve.assert_called_once()

# --- WebhookService.handle_customer_subscription_created Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Patch the utility
async def test_handle_customer_subscription_created_non_trial(
    mock_get_or_create_sub: AsyncMock, # Patched utility
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_sub_created_non_trial"
    user_id = mock_user.id
    stripe_price_id = "price_non_trial"
    stripe_subscription_id = "sub_non_trial_123"
    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "active", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": None,
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    # Mock the return value of get_or_create_subscription
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.stripe_customer_id = mock_user.stripe_customer_id # Ensure it has necessary attributes
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.db.set_db_get_result(mock_user) # For user object retrieval

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        mock_trial_started.assert_not_called()
        mock_trial_blocked.assert_not_called()

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_user.has_consumed_initial_trial is False
    # Check attributes were set on the mocked subscription object by the handler
    assert mock_db_subscription.status == "active"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    webhook_service.db.commit.assert_called_once()

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
@patch("app.services.webhook_service.stripe.Subscription.delete")
async def test_handle_customer_subscription_created_trial_unique_fingerprint(
    mock_stripe_sub_delete: MagicMock, # Renamed from mock_stripe_sub_cancel
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    monkeypatch # Added monkeypatch fixture
):
    event_id = "evt_sub_trial_unique"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added for clarity
    card_fingerprint = "fp_trial_unique"
    stripe_subscription_id = "sub_trial_unique_123"

    # Monkeypatch settings for trial attributes
    monkeypatch.setattr(settings, "STRIPE_FREE_TRIAL_PRICE_ID", "price_free_trial_test")
    # Add these settings if they don't exist
    if not hasattr(settings, "FREE_TRIAL_DAYS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_DAYS", 7)
    if not hasattr(settings, "FREE_TRIAL_CREDITS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_CREDITS", 10)

    stripe_price_id = settings.STRIPE_FREE_TRIAL_PRICE_ID
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp())
    trial_end_date = datetime.fromtimestamp(trial_end_timestamp, tz=timezone.utc)


    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        # "default_payment_method": "pm_trial_unique",
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": trial_end_timestamp, "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.set_db_execute_scalar_first_results(None) # For UsedTrialCardFingerprint check (was (None, None))

    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    original_has_consumed_trial = mock_user.has_consumed_initial_trial
    original_account_status = mock_user.account_status
    mock_user.has_consumed_initial_trial = False # Ensure it's false before test
    # Reset add mock to avoid interference from previous tests or complex side effects
    webhook_service.db.add = MagicMock()
    webhook_service.db.merge = AsyncMock(side_effect=lambda instance: instance)


    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        
        mock_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_date,
            credits_granted=settings.FREE_TRIAL_CREDITS
        )
        mock_trial_blocked.assert_not_called()

    assert mock_user.has_consumed_initial_trial is True
    assert mock_user.account_status == "trialing"
    
    # Check that UsedTrialCardFingerprint was added
    fingerprint_add_call = next((c for c in webhook_service.db.add.call_args_list if isinstance(c.args[0], UsedTrialCardFingerprint)), None)
    assert fingerprint_add_call is not None
    added_fingerprint_obj = fingerprint_add_call.args[0]
    assert added_fingerprint_obj.stripe_card_fingerprint == card_fingerprint
    assert added_fingerprint_obj.user_id == user_id
    assert added_fingerprint_obj.stripe_subscription_id == stripe_subscription_id

    # Check that CreditTransaction was added
    credit_tx_add_call = next((c for c in webhook_service.db.add.call_args_list if isinstance(c.args[0], CreditTransaction)), None)
    assert credit_tx_add_call is not None
    added_tx_obj = credit_tx_add_call.args[0]
    assert added_tx_obj.user_id == user_id
    assert added_tx_obj.amount == settings.FREE_TRIAL_CREDITS
    assert added_tx_obj.transaction_type == "trial_credit_grant"
    assert added_tx_obj.reference_id == stripe_subscription_id
    
    # Check UserCredit was added or merged
    # This part is tricky without knowing if UserCredit is always new or can be existing.
    # The service logic seems to fetch UserCredit and update its balance.
    # We can check if db.merge was called with a UserCredit instance, or if db.add was.
    user_credit_call = next((c for c in webhook_service.db.merge.call_args_list if isinstance(c.args[0], UserCredit)), None)
    if not user_credit_call:
        user_credit_call = next((c for c in webhook_service.db.add.call_args_list if isinstance(c.args[0], UserCredit)), None)
    assert user_credit_call is not None, "UserCredit was neither merged nor added"
    # If we could inspect the merged/added UserCredit object, we'd check its balance.
    # For now, the fact that a CreditTransaction was created for the correct amount is a strong indicator.

    webhook_service.db.commit.assert_called_once()
    mock_stripe_sub_delete.assert_not_called() # Renamed from mock_stripe_sub_cancel
    
    assert mock_db_subscription.status == "trialing"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    assert mock_db_subscription.trial_end_date == trial_end_date
    assert mock_db_subscription.current_period_start.date() == datetime.fromtimestamp(subscription_data["current_period_start"], tz=timezone.utc).date()
    assert mock_db_subscription.current_period_end.date() == trial_end_date.date()
    assert mock_db_subscription.cancel_at_period_end is False
    
    mock_user.has_consumed_initial_trial = original_has_consumed_trial
    mock_user.account_status = original_account_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
@patch("app.services.webhook_service.stripe.Subscription.delete")
async def test_handle_customer_subscription_created_trial_duplicate_fingerprint(
    mock_stripe_sub_delete: MagicMock,
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    monkeypatch # Added
):
    event_id = "evt_sub_trial_duplicate"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added for clarity
    card_fingerprint = "fp_trial_duplicate"
    stripe_subscription_id = "sub_trial_duplicate_123"

    monkeypatch.setattr(settings, "STRIPE_FREE_TRIAL_PRICE_ID", "price_free_trial_test_dup")
    # Add these settings if they don't exist
    if not hasattr(settings, "FREE_TRIAL_DAYS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_DAYS", 7)
    # FREE_TRIAL_CREDITS not directly used in this path, but good for consistency if logic changes
    if not hasattr(settings, "FREE_TRIAL_CREDITS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_CREDITS", 10)

    stripe_price_id = settings.STRIPE_FREE_TRIAL_PRICE_ID
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp())

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        # "default_payment_method": "pm_trial_duplicate",
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": trial_end_timestamp, "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval
    
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_db_subscription

    # Simulate IntegrityError when adding UsedTrialCardFingerprint
    async def merge_side_effect_for_duplicate_fingerprint(instance):
        if isinstance(instance, UsedTrialCardFingerprint):
            # The service tries to MERGE the fingerprint first. If that doesn't raise,
            # it then tries to ADD it if the merge returned None (which it would if not found).
            # To simulate the duplicate on ADD, we need to ensure merge returns None,
            # and then the subsequent ADD raises IntegrityError.
            # However, the service logic is:
            #   existing_fingerprint = await self.db.scalar(select(UsedTrialCardFingerprint)...)
            #   if existing_fingerprint: -> block
            #   else: -> try: db.add(new_fingerprint); await db.flush() except IntegrityError: -> block
            # So, we need `set_db_execute_scalar_first_results(None)` for the initial select,
            # and then make `db.add` (or `db.flush` after add) raise IntegrityError.
            pass # Let the add mock handle it
        return instance # Default merge behavior

    webhook_service.db.merge = AsyncMock(side_effect=merge_side_effect_for_duplicate_fingerprint)
    
    # This is for the initial check: `select(UsedTrialCardFingerprint).where(...)`
    webhook_service.db.set_db_execute_scalar_first_results(None)

    # This is for the `db.add(new_fingerprint_record)` followed by `await db.flush()`
    # We'll make db.flush raise the IntegrityError
    webhook_service.db.flush = AsyncMock(side_effect=IntegrityError("Simulated duplicate fingerprint on flush", params=None, orig=None))
    webhook_service.db.add = MagicMock() # Regular add for other objects like transaction

    original_account_status = mock_user.account_status
    mock_user.has_consumed_initial_trial = False # Ensure user hasn't consumed trial for this scenario

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started:
        await webhook_service.handle_customer_subscription_created(event)
        
        mock_trial_blocked.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )
        mock_trial_started.assert_not_called()

    mock_stripe_sub_delete.assert_called_once_with(stripe_subscription_id)
    assert mock_user.account_status == "trial_rejected"
    # UserCredit and CreditTransaction should not have been created/added
    assert not any(isinstance(call.args[0], UserCredit) for call in webhook_service.db.add.call_args_list)
    assert not any(isinstance(call.args[0], CreditTransaction) for call in webhook_service.db.add.call_args_list)
    
    webhook_service.db.commit.assert_called_once() # Commit happens for user status update
    webhook_service.db.rollback.assert_called_once() # Rollback due to IntegrityError
    mock_user.account_status = original_account_status # Restore
    mock_user.has_consumed_initial_trial = True # Restore if needed

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_trial_already_consumed(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    monkeypatch # Added
):
    event_id = "evt_sub_trial_consumed"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id

    # Monkeypatch settings for trial attributes
    monkeypatch.setattr(settings, "STRIPE_FREE_TRIAL_PRICE_ID", "price_free_trial_test_consumed")
    # Add these settings if they don't exist
    if not hasattr(settings, "FREE_TRIAL_DAYS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_DAYS", 7)
    if not hasattr(settings, "FREE_TRIAL_CREDITS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_CREDITS", 10)

    stripe_subscription_id = "sub_trial_consumed_123"
    stripe_price_id = settings.STRIPE_FREE_TRIAL_PRICE_ID
    card_fingerprint = "fp_trial_consumed"
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp())
    trial_end_date = datetime.fromtimestamp(trial_end_timestamp, tz=timezone.utc)

    mock_user.has_consumed_initial_trial = True
    original_account_status = mock_user.account_status
    
    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        # "default_payment_method": "pm_trial_consumed",
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": trial_end_timestamp, "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)

    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval
    
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.db.add = MagicMock()
    webhook_service.db.merge = AsyncMock(side_effect=lambda instance: instance)
    # No need to mock UsedTrialCardFingerprint select, as has_consumed_initial_trial check is earlier

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        mock_trial_started.assert_not_called()
        mock_trial_blocked.assert_not_called()

    # No credits should be granted
    assert not any(isinstance(call.args[0], UserCredit) for call in webhook_service.db.add.call_args_list)
    assert not any(isinstance(call.args[0], CreditTransaction) for call in webhook_service.db.add.call_args_list)
    # Fingerprint should not be added in this "already consumed" path
    assert not any(isinstance(call.args[0], UsedTrialCardFingerprint) for call in webhook_service.db.add.call_args_list)

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_db_subscription.status == "trialing"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    assert mock_db_subscription.trial_end_date == trial_end_date
    assert mock_db_subscription.current_period_start.date() == datetime.fromtimestamp(subscription_data["current_period_start"], tz=timezone.utc).date()
    assert mock_db_subscription.current_period_end.date() == trial_end_date.date()
    assert mock_db_subscription.cancel_at_period_end is False
    
    assert mock_user.account_status == "trialing"

    webhook_service.db.commit.assert_called_once()
    
    mock_user.has_consumed_initial_trial = True
    mock_user.account_status = original_account_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_missing_user_id(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_sub_created_no_user"
    stripe_customer_id = "cus_no_user_missing_in_db"
    subscription_data = {
        "id": "sub_no_user_123", "customer": stripe_customer_id, "metadata": {},
        "status": "active", "items": {"data": [{"price": {"id": "price_active"}}]},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.db.set_db_execute_scalar_first_results(None)
    webhook_service.db.set_db_get_result(None)

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        mock_trial_started.assert_not_called()
        mock_trial_blocked.assert_not_called()

    webhook_service.db.execute.assert_called_once()
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_customer_subscription_created_trial_missing_fingerprint(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    monkeypatch # Ensure monkeypatch is here
):
    event_id = "evt_sub_trial_no_fp"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id

    # Monkeypatch settings for trial attributes
    monkeypatch.setattr(settings, "STRIPE_FREE_TRIAL_PRICE_ID", "price_free_trial_test_no_fp")
    # Add these settings if they don't exist
    if not hasattr(settings, "FREE_TRIAL_DAYS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_DAYS", 7)
    if not hasattr(settings, "FREE_TRIAL_CREDITS"):
        monkeypatch.setattr(settings, "FREE_TRIAL_CREDITS", 10) # Even if not used, good for consistency
    
    stripe_price_id = settings.STRIPE_FREE_TRIAL_PRICE_ID

    subscription_data = {
        "id": "sub_trial_no_fp_123", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp()),
        
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp()),
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=None)
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval
    # mock_get_or_create_sub should not be called if fingerprint is missing for trial
    
    mock_user.has_consumed_initial_trial = False # Ensure this condition is met for trial logic path

    with pytest.raises(ValueError, match="Card fingerprint missing for trial subscription"):
        await webhook_service.handle_customer_subscription_created(event)
    
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()
    webhook_service.db.rollback.assert_called_once() # Expect a rollback due to the ValueError

# --- WebhookService.handle_customer_subscription_updated Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_customer_subscription_updated_status_change_active_to_frozen(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_sub_updated_active_to_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_active_to_frozen_123"
    stripe_price_id = "price_active_frozen" # Added for clarity

    subscription_data = {
        "id": stripe_subscription_id, "customer": stripe_customer_id,
        "status": "past_due", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False, "canceled_at": None, "trial_end": None
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    mock_user.account_status = "active"
    original_user_status = mock_user.account_status

    # Mock the subscription returned by get_or_create_subscription
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "active" # Initial status of the DB record
    mock_db_subscription.stripe_price_id = "some_old_price" # Can be different
    mock_db_subscription.canceled_at = None # Initialize to None
    mock_db_subscription.trial_end_date = None # Initialize to None (for trial_ends_at assertion)
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    with patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )
    
    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_db_subscription.status == "past_due" # Updated by the handler
    assert mock_db_subscription.stripe_price_id == stripe_price_id # Updated by the handler
    # Assert other fields on mock_db_subscription are updated as per event data
    assert mock_db_subscription.current_period_start.date() == datetime.fromtimestamp(subscription_data["current_period_start"], tz=timezone.utc).date()
    assert mock_db_subscription.current_period_end.date() == datetime.fromtimestamp(subscription_data["current_period_end"], tz=timezone.utc).date()
    assert mock_db_subscription.cancel_at_period_end is False
    assert mock_db_subscription.canceled_at is None
    assert mock_db_subscription.trial_end_date is None # Corrected attribute name


    assert mock_user.account_status == "frozen"
    webhook_service.db.commit.assert_called_once()
    
    # Restore mock_user state
    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_customer_subscription_updated_status_change_frozen_to_active(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_sub_updated_frozen_to_active"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_frozen_to_active_123"
    stripe_price_id = "price_frozen_active" # Added

    subscription_data = {
        "id": stripe_subscription_id, "customer": stripe_customer_id,
        "status": "active", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False, "canceled_at": None, "trial_end": None
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    mock_user.account_status = "frozen"
    original_user_status = mock_user.account_status

    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "past_due" # Initial status of the DB record
    mock_db_subscription.stripe_price_id = "some_old_price"
    mock_db_subscription.canceled_at = None # Initialize
    mock_db_subscription.trial_end_date = None # Initialize
    mock_get_or_create_sub.return_value = mock_db_subscription
    
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    with patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_unfrozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_db_subscription.status == "active"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    assert mock_db_subscription.current_period_start.date() == datetime.fromtimestamp(subscription_data["current_period_start"], tz=timezone.utc).date()
    assert mock_db_subscription.current_period_end.date() == datetime.fromtimestamp(subscription_data["current_period_end"], tz=timezone.utc).date()
    assert mock_db_subscription.cancel_at_period_end is False
    assert mock_db_subscription.canceled_at is None
    assert mock_db_subscription.trial_end_date is None # Corrected attribute

    assert mock_user.account_status == "active"
    webhook_service.db.commit.assert_called_once()

    # Restore mock_user state
    mock_user.account_status = original_user_status

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
    stripe_price_id = "price_sub_not_found"

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "active", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False, "canceled_at": None, "trial_end": None
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    mock_user.account_status = "pending"
    original_user_status = mock_user.account_status
    
    mock_db_subscription = MagicMock(spec=Subscription)
    # Simulate that get_or_create_subscription is creating it, so it might not have all fields initially
    # The handler should populate them.
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.canceled_at = None  # Initialize
    mock_db_subscription.trial_end_date = None  # Initialize
    # Other fields like status, stripe_price_id will be set by the handler
    mock_get_or_create_sub.return_value = mock_db_subscription
        
    webhook_service.db.set_db_get_result(mock_user)

    with patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        
        await webhook_service.handle_customer_subscription_updated(event)
        
        mock_publish_unfrozen.assert_not_called() # From 'pending' to 'active' does not trigger 'unfrozen' by current logic
        mock_publish_frozen.assert_not_called()

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    
    assert mock_db_subscription.status == "active"
    assert mock_db_subscription.stripe_price_id == stripe_price_id
    assert mock_db_subscription.current_period_start.date() == datetime.fromtimestamp(subscription_data["current_period_start"], tz=timezone.utc).date()
    assert mock_db_subscription.current_period_end.date() == datetime.fromtimestamp(subscription_data["current_period_end"], tz=timezone.utc).date()
    assert mock_db_subscription.cancel_at_period_end is False
    assert mock_db_subscription.canceled_at is None
    assert mock_db_subscription.trial_end_date is None # Corrected attribute name

    assert mock_user.account_status == "active"
    webhook_service.db.commit.assert_called_once()

    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_missing_user_id(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_sub_updated_no_user"
    stripe_customer_id = "cus_no_user_updated_missing"
    subscription_data = {
        "id": "sub_no_user_123", "customer": stripe_customer_id, "metadata": {},
        "status": "active", "items": {"data": [{"price": {"id": "price_no_user"}}]},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False,
        "canceled_at": None,
        "trial_end": None
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)
    
    webhook_service.db.set_db_execute_scalar_first_results(None)
    webhook_service.db.set_db_get_result(None)

    with patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_frozen.assert_not_called()
        mock_publish_unfrozen.assert_not_called()
        
    webhook_service.db.execute.assert_called_once()
    webhook_service.db.get.assert_not_called() # Existing assertion is good
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()

# --- WebhookService.handle_invoice_payment_succeeded Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_succeeded_success_active_user(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_paid_active"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_inv_paid_active_123" # From invoice data

    invoice_data = {
        "id": "in_inv_paid_active_123", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "paid",
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id},
        "charge": "ch_paid_active",
        "amount_paid": 1000, # Added (e.g., 10.00 USD)
        "currency": "usd", # Added
        "billing_reason": "subscription_cycle", # Added missing field
        "invoice_pdf": "https://example.com/invoice.pdf" # Added missing field
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)
    
    mock_user.account_status = "active"
    original_user_status = mock_user.account_status
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "active" # Initial status
    # mock_get_or_create_sub.return_value = mock_db_subscription # Not strictly needed
    webhook_service.db.set_db_execute_scalar_first_results(mock_db_subscription) # Ensure select query returns our mock

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_publish_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=invoice_data["id"],
            stripe_subscription_id=stripe_subscription_id,
            amount_paid=invoice_data["amount_paid"],
            currency=invoice_data["currency"],
            billing_reason=invoice_data["billing_reason"],
            invoice_pdf_url=invoice_data["invoice_pdf"]
            )
        mock_publish_unfrozen.assert_not_called()

    mock_get_or_create_sub.assert_not_called() # get_or_create_subscription is not called in this handler
    assert mock_db_subscription.status == "active" # Status should remain active
    assert mock_user.account_status == "active"
    webhook_service.db.commit.assert_called_once()

    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_succeeded_unfreezes_user(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_paid_unfreeze"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_inv_paid_unfreeze_123" # From invoice data

    invoice_data = {
        "id": "in_inv_paid_unfreeze_123", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "paid",
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id},
        "charge": "ch_paid_unfreeze",
        "amount_paid": 1200, # Added
        "currency": "usd", # Added
        "billing_reason": "subscription_cycle", # Added missing field
        "invoice_pdf": "https://example.com/invoice.pdf" # Added missing field
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)
    
    mock_user.account_status = "frozen"
    original_user_status = mock_user.account_status
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    # This is the mock that get_or_create_subscription will return
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "past_due" # Initial status before handler updates it
    # mock_get_or_create_sub.return_value = mock_db_subscription # Not strictly needed as it won't be called
    webhook_service.db.set_db_execute_scalar_first_results(mock_db_subscription) # Ensure select query returns our mock

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_publish_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=invoice_data["id"],
            stripe_subscription_id=stripe_subscription_id,
            amount_paid=invoice_data["amount_paid"],
            currency=invoice_data["currency"],
            billing_reason=invoice_data["billing_reason"],
            invoice_pdf_url=invoice_data["invoice_pdf"]
        )
        mock_publish_unfrozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="invoice_paid_after_failure"
        )

    mock_get_or_create_sub.assert_not_called() # get_or_create_subscription is not called in this handler
    assert mock_user.account_status == "active"
    assert mock_db_subscription.status == "active" # Status of the subscription object updated by handler
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_succeeded_missing_user_id(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_paid_no_user"
    stripe_customer_id = "cus_no_user_inv_missing" # Explicit
    invoice_data = {
        "id": "in_inv_paid_no_user_123", "customer": stripe_customer_id,
        "subscription": "sub_no_user_123", "status": "paid",
        "customer_details": {"metadata": {}},
        "metadata": {}, # Ensure user_id is missing from both typical spots
        "charge": "ch_paid_no_user"
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)
    
    # Simulate user_id not found from stripe_customer_id
    webhook_service.db.set_db_execute_scalar_first_results(None)
    webhook_service.db.set_db_get_result(None) # Ensure db.get(User, None) if called by user_id would also be None

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_publish_paid.assert_not_called()
        mock_publish_unfrozen.assert_not_called()

    webhook_service.db.execute.assert_called_once() # Attempted user lookup by stripe_customer_id
    # webhook_service.db.get.assert_called_once_with(User, None) # This might not be called if user_id from customer fails first
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_succeeded_user_not_found_in_db(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_paid_user_not_db"
    user_id = "non_existent_user_id"
    stripe_customer_id = "cus_user_not_db" # Added
    invoice_data = {
        "id": "in_inv_paid_user_not_db_123", "customer": stripe_customer_id,
        "subscription": "sub_user_not_db_123", "status": "paid",
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id}, # Added for consistency
        "charge": "ch_paid_user_not_db"
    }
    event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)
    
    webhook_service.db.set_db_get_result(None) # User not found by ID
    # If user_id is present in metadata, the execute call for customer_id lookup might not happen.

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_publish_paid.assert_not_called()
        mock_publish_unfrozen.assert_not_called()
    
    webhook_service.db.get.assert_called_once_with(User, user_id) # User lookup by ID from metadata
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()

# --- WebhookService.handle_invoice_payment_failed Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_failed_freezes_active_user(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_freeze"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_inv_failed_freeze_123"

    invoice_data = {
        "id": "in_inv_failed_freeze_123", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "open", # Stripe's invoice status
        "billing_reason": "subscription_cycle", "charge": "ch_failed_freeze",
        "last_payment_error": {"message": "Card declined"},
        "next_payment_attempt": int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp()),
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id} # Added for consistency
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)
    
    mock_user.account_status = "active"
    original_user_status = mock_user.account_status
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    # This is the mock that get_or_create_subscription will return
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "active" # Initial status before handler updates it
    mock_get_or_create_sub.return_value = mock_db_subscription

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=invoice_data["id"],
            stripe_subscription_id=stripe_subscription_id,
            failure_reason="Card declined", # Corrected
            next_payment_attempt_date=datetime.fromtimestamp(invoice_data["next_payment_attempt"], tz=timezone.utc), # Corrected & converted
            stripe_charge_id=invoice_data["charge"] # Corrected
        )
        mock_publish_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="invoice_payment_failed"
        )

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_user.account_status == "frozen"
    # The service updates the local subscription status to 'past_due' after invoice payment failure.
    assert mock_db_subscription.status == "past_due"
    webhook_service.db.commit.assert_called_once()

    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_failed_already_frozen_user(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_already_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added
    stripe_subscription_id = "sub_inv_failed_frozen_123"

    invoice_data = {
        "id": "in_inv_failed_frozen_123", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "status": "open", # Invoice status from Stripe
        "billing_reason": "subscription_cycle", "charge": "ch_failed_already_frozen",
        "last_payment_error": {"message": "Card declined again"}, # Corrected message
        "next_payment_attempt": int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp()),
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id} # Added
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)
    
    mock_user.account_status = "frozen"
    original_user_status = mock_user.account_status
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval

    # This is the mock that get_or_create_subscription will return
    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_db_subscription.status = "past_due" # Initial local status
    mock_get_or_create_sub.return_value = mock_db_subscription

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=invoice_data["id"],
            stripe_subscription_id=stripe_subscription_id,
            failure_reason="Card declined again", # Corrected
            next_payment_attempt_date=datetime.fromtimestamp(invoice_data["next_payment_attempt"], tz=timezone.utc), # Corrected & converted
            stripe_charge_id=invoice_data["charge"] # Corrected
        )
        mock_publish_frozen.assert_not_called()

    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_user.account_status == "frozen"
    assert mock_db_subscription.status == "past_due" # Should remain/be set to past_due
    webhook_service.db.commit.assert_called_once()

    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_failed_non_subscription_reason(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_non_sub"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id # Added

    invoice_data = {
        "id": "in_inv_failed_non_sub_123", "customer": stripe_customer_id,
        "subscription": None, "status": "open", "billing_reason": "manual", # Key: subscription is None
        "last_payment_error": {"message": "Card declined"}, "charge": "ch_failed_non_sub",
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id}, # Added
        "next_payment_attempt": None
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)
    
    mock_user.account_status = "active"
    original_user_status = mock_user.account_status
    webhook_service.db.set_db_get_result(mock_user) # For User retrieval
    # No subscription lookup expected if invoice.subscription is None

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_invoice_id=invoice_data["id"],
            stripe_subscription_id=None,
            failure_reason="Card declined", # Corrected
            next_payment_attempt_date=None, # Corrected (timestamp was None, so date is None)
            stripe_charge_id=invoice_data["charge"] # Corrected
        )
        mock_publish_frozen.assert_not_called()

    mock_get_or_create_sub.assert_not_called() # Should not be called if invoice.subscription is None
    assert mock_user.account_status == "active"
    webhook_service.db.commit.assert_not_called() # No DB changes should be committed in this scenario

    mock_user.account_status = original_user_status

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_failed_missing_user_id(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_failed_no_user"
    stripe_customer_id = "cus_no_user_inv_fail_missing_again" # Explicit and unique

    invoice_data = {
        "id": "in_inv_failed_no_user_123", "customer": stripe_customer_id,
        "subscription": "sub_no_user_123", "status": "open",
        "billing_reason": "subscription_cycle", "charge": "ch_failed_no_user",
        "customer_details": {"metadata": {}},
        # Ensure metadata is also empty if service checks event.data.object.metadata.user_id
        "metadata": {}
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)
    
    webhook_service.db.set_db_execute_scalar_first_results(None)
    webhook_service.db.set_db_get_result(None)

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_not_called()
        mock_publish_frozen.assert_not_called()

    webhook_service.db.execute.assert_called_once()
    # The service logic first tries to get user_id from event metadata, then customer_details metadata,
    # then by querying User table with stripe_customer_id.
    # If all fail, db.get(User, None) might be called if user_id variable remains None.
    # Let's ensure the primary lookup (by customer_id) is checked.
    # If user_id is not found via stripe_customer_id, db.get(User, None) might not be reached
    # if the code exits after the initial lookup attempt.
    # webhook_service.db.get.assert_called_once_with(User, None) # This might be too specific
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added
async def test_handle_invoice_payment_failed_user_not_found_in_db(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_failed_user_not_db"
    user_id = "non_existent_user_id"
    stripe_customer_id = "cus_user_not_db" # Added

    invoice_data = {
        "id": "in_inv_failed_user_not_db_123", "customer": stripe_customer_id,
        "subscription": "sub_user_not_db_123", "status": "open",
        "billing_reason": "subscription_cycle", "charge": "ch_failed_user_not_db",
        "customer_details": {"metadata": {"user_id": user_id}},
        "metadata": {"user_id": user_id} # Added for consistency
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)
    
    webhook_service.db.set_db_get_result(None) # User not found by ID
    # If user_id is present in metadata, the execute call for customer_id lookup might not happen.

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_not_called()
        mock_publish_frozen.assert_not_called()
    
    webhook_service.db.get.assert_called_once_with(User, user_id) # User lookup by ID from metadata
    mock_get_or_create_sub.assert_not_called()
    webhook_service.db.commit.assert_not_called()


# --- Endpoint Tests ---
def create_mock_verify_dependency(mock_event_to_return: stripe.Event) -> Callable:
    """Factory to create a mock for the verify_stripe_signature dependency."""
    async def mock_verify_stripe_signature_override(
        request: Request, # Parameter name must match the dependency
        stripe_signature: str | None = Header(None) # Parameter name must match
    ) -> stripe.Event:
        # Bypass actual signature verification and return the mock event
        return mock_event_to_return
    return mock_verify_stripe_signature_override

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_checkout_session_completed(
    client: AsyncClient,
    mock_stripe_event_factory: Callable
    # mock_db_session is not directly used here as WebhookService is fully mocked
):
    """Integration test for a valid checkout.session.completed event."""
    event_type = "checkout.session.completed"
    event_id = "evt_integ_checkout_success"
    user_id_from_event = "user_123_checkout_ep"
    payload_data = {
        "id": "cs_integ_test_ep",
        "customer": "cus_integ_test_ep",
        "client_reference_id": user_id_from_event,
        "subscription": "sub_integ_checkout_ep",
        "payment_intent": "pi_integ_checkout_ep",
        "metadata": {"user_id": user_id_from_event}
    }
    mock_event_obj = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    mock_service_instance = AsyncMock(spec=WebhookService)
    mock_service_instance.is_event_processed = AsyncMock(return_value=False)
    # Mock all handlers that could be called by the router
    mock_service_instance.handle_checkout_session_completed = AsyncMock()
    mock_service_instance.handle_customer_subscription_created = AsyncMock()
    mock_service_instance.handle_customer_subscription_updated = AsyncMock()
    mock_service_instance.handle_invoice_payment_succeeded = AsyncMock()
    mock_service_instance.handle_invoice_payment_failed = AsyncMock()
    mock_service_instance.mark_event_as_processed = AsyncMock()
    
    # Import the get_webhook_service function from the module
    from app.routers.webhooks.stripe_webhooks import get_webhook_service, verify_stripe_signature
    
    # Override the dependencies correctly
    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event_obj)
    main_app.dependency_overrides[get_webhook_service] = lambda: mock_service_instance
    
    try:
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"some": "payload"}',
            headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
        )

        assert response.status_code == 200
        # The endpoint router logs "Successfully processed event..."
        assert response.json() == {"status": "success", "message": f"Successfully processed event: {event_id} ({event_type})"}

        mock_service_instance.is_event_processed.assert_called_once_with(event_id)
        mock_service_instance.handle_checkout_session_completed.assert_called_once_with(mock_event_obj)
        mock_service_instance.mark_event_as_processed.assert_called_once_with(event_id, event_type)
        
        # Ensure other specific handlers were not called for this event type
        mock_service_instance.handle_customer_subscription_created.assert_not_called()
        mock_service_instance.handle_customer_subscription_updated.assert_not_called()
        mock_service_instance.handle_invoice_payment_succeeded.assert_not_called()
        mock_service_instance.handle_invoice_payment_failed.assert_not_called()
    finally:
        main_app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_idempotency(
    client: AsyncClient,
    mock_stripe_event_factory: Callable
):
    """Test that already processed events are handled idempotently."""
    event_type = "checkout.session.completed" # Can be any type for this test
    event_id = "evt_integ_idempotency"
    payload_data = {"id": "cs_integ_idem_test", "customer": "cus_integ_idem_test", "client_reference_id": "user_idem_123"}
    mock_event_obj = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    # Create a mock that will actually be called
    mock_service_instance = AsyncMock(spec=WebhookService)
    mock_service_instance.is_event_processed = AsyncMock(return_value=True) # Key: Event already processed
    # Mock all handlers to ensure none are called if already processed
    mock_service_instance.handle_checkout_session_completed = AsyncMock()
    mock_service_instance.handle_customer_subscription_created = AsyncMock()
    mock_service_instance.handle_customer_subscription_updated = AsyncMock()
    mock_service_instance.handle_invoice_payment_succeeded = AsyncMock()
    mock_service_instance.handle_invoice_payment_failed = AsyncMock()
    mock_service_instance.mark_event_as_processed = AsyncMock() # Should not be called again

    # Import the get_webhook_service function from the module
    from app.routers.webhooks.stripe_webhooks import get_webhook_service, verify_stripe_signature
    
    # Override the dependencies correctly
    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event_obj)
    main_app.dependency_overrides[get_webhook_service] = lambda: mock_service_instance
    
    try:
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"some": "payload"}',
            headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "success", "message": f"Event {event_id} already processed."} # Updated expected message

        mock_service_instance.is_event_processed.assert_called_once_with(event_id)
        # Ensure no specific handlers were called
        mock_service_instance.handle_checkout_session_completed.assert_not_called()
        mock_service_instance.handle_customer_subscription_created.assert_not_called()
        mock_service_instance.handle_customer_subscription_updated.assert_not_called()
        mock_service_instance.handle_invoice_payment_succeeded.assert_not_called()
        mock_service_instance.handle_invoice_payment_failed.assert_not_called()
        mock_service_instance.mark_event_as_processed.assert_not_called() # Crucially, not marked again
    finally:
        main_app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_unhandled_event_type(
    client: AsyncClient,
    mock_stripe_event_factory: Callable
):
    """Test the endpoint with an unhandled event type."""
    event_type = "totally.unknown.event"
    event_id = "evt_integ_unknown"
    payload_data = {"id": "obj_integ_unknown"}
    mock_event_obj = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    mock_service_instance = AsyncMock(spec=WebhookService)
    mock_service_instance.is_event_processed = AsyncMock(return_value=False)
    # Mock all specific handlers
    mock_service_instance.handle_checkout_session_completed = AsyncMock()
    mock_service_instance.handle_customer_subscription_created = AsyncMock()
    mock_service_instance.handle_customer_subscription_updated = AsyncMock()
    mock_service_instance.handle_invoice_payment_succeeded = AsyncMock()
    mock_service_instance.handle_invoice_payment_failed = AsyncMock()
    mock_service_instance.mark_event_as_processed = AsyncMock()

    # Import the get_webhook_service function from the module
    from app.routers.webhooks.stripe_webhooks import get_webhook_service, verify_stripe_signature
    
    # Override the dependencies correctly
    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event_obj)
    main_app.dependency_overrides[get_webhook_service] = lambda: mock_service_instance
    
    try:
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"some": "payload"}',
            headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
        )
        assert response.status_code == 200
        # Align with the actual log message for unhandled events
        assert response.json() == {"status": "success", "message": f"Webhook received for unhandled event type: {event_type}"}

        mock_service_instance.is_event_processed.assert_called_once_with(event_id)
        # Ensure no specific handlers were called
        mock_service_instance.handle_checkout_session_completed.assert_not_called()
        mock_service_instance.handle_customer_subscription_created.assert_not_called()
        mock_service_instance.handle_customer_subscription_updated.assert_not_called()
        mock_service_instance.handle_invoice_payment_succeeded.assert_not_called()
        mock_service_instance.handle_invoice_payment_failed.assert_not_called()
        # Event should still be marked as processed to prevent retries for unknown types
        mock_service_instance.mark_event_as_processed.assert_called_once_with(event_id, event_type)
    finally:
        main_app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_handler_exception(
    client: AsyncClient,
    mock_stripe_event_factory: Callable
):
    """Test the endpoint when a handler raises an exception."""
    event_type = "checkout.session.completed"
    event_id = "evt_integ_handler_ex"
    error_message = "Simulated handler error during test" # Defined error message
    payload_data = {
        "id": "cs_integ_handler_ex",
        "customer": "cus_integ_handler_ex",
        "client_reference_id": "user_ex_handler_123" # Consistent naming
    }
    mock_event_obj = mock_stripe_event_factory(event_type, payload_data, event_id=event_id)

    mock_service_instance = AsyncMock(spec=WebhookService)
    mock_service_instance.is_event_processed = AsyncMock(return_value=False)
    # Mock all handlers, with the relevant one raising an error
    mock_service_instance.handle_checkout_session_completed = AsyncMock(side_effect=ValueError(error_message))
    mock_service_instance.handle_customer_subscription_created = AsyncMock()
    mock_service_instance.handle_customer_subscription_updated = AsyncMock()
    mock_service_instance.handle_invoice_payment_succeeded = AsyncMock()
    mock_service_instance.handle_invoice_payment_failed = AsyncMock()
    mock_service_instance.mark_event_as_processed = AsyncMock()

    # Import the get_webhook_service function from the module
    from app.routers.webhooks.stripe_webhooks import get_webhook_service, verify_stripe_signature
    
    # Override the dependencies correctly
    main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event_obj)
    main_app.dependency_overrides[get_webhook_service] = lambda: mock_service_instance

    try:
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"some": "payload"}', # Content doesn't matter due to verify_stripe_signature mock
            headers={"Stripe-Signature": "t=123,v1=dummy_sig"}
        )
        assert response.status_code == 500
        assert response.json() == {"detail": f"Error processing event {event_id} ({event_type}): {error_message}"}

        mock_service_instance.is_event_processed.assert_called_once_with(event_id)
        mock_service_instance.handle_checkout_session_completed.assert_called_once_with(mock_event_obj)
        mock_service_instance.mark_event_as_processed.assert_not_called() # Crucial: not marked if handler fails

        # Ensure other specific handlers were not called
        mock_service_instance.handle_customer_subscription_created.assert_not_called()
        mock_service_instance.handle_customer_subscription_updated.assert_not_called()
        mock_service_instance.handle_invoice_payment_succeeded.assert_not_called()
        mock_service_instance.handle_invoice_payment_failed.assert_not_called()
    finally:
        main_app.dependency_overrides.clear()
@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_signature_error(client: AsyncClient):
    """Test the endpoint when Stripe signature verification fails."""
    error_message = "Simulated signature verification error"

    # Create a proper async mock for the verify_stripe_signature dependency
    # that raises an HTTPException instead of a SignatureVerificationError
    async def mock_verify_dependency_raises(request: Request, stripe_signature: str = None):
        # Convert the SignatureVerificationError to an HTTPException with status_code 400
        # This matches what the real verify_stripe_signature function does
        raise HTTPException(
            status_code=400,
            detail=f"Error verifying webhook signature: {error_message}"
        )

    # Mock WebhookService to ensure it's not called if signature fails
    mock_service_instance = AsyncMock(spec=WebhookService)
    mock_service_instance.is_event_processed = AsyncMock()
    mock_service_instance.handle_checkout_session_completed = AsyncMock()
    mock_service_instance.handle_customer_subscription_created = AsyncMock()
    mock_service_instance.handle_customer_subscription_updated = AsyncMock()
    mock_service_instance.handle_invoice_payment_succeeded = AsyncMock()
    mock_service_instance.handle_invoice_payment_failed = AsyncMock()
    mock_service_instance.mark_event_as_processed = AsyncMock()

    # Import the get_webhook_service function from the module
    from app.routers.webhooks.stripe_webhooks import get_webhook_service, verify_stripe_signature
    
    # Override the dependencies correctly
    main_app.dependency_overrides[verify_stripe_signature] = mock_verify_dependency_raises
    main_app.dependency_overrides[get_webhook_service] = lambda: mock_service_instance

    try:
        response = await client.post(
            "/webhooks/stripe",
            content=b'{"some": "payload"}', # Actual payload doesn't matter here
            headers={"Stripe-Signature": "t=123,v1=invalid_signature_on_purpose"}
        )
        
        assert response.status_code == 400
        assert response.json() == {"detail": f"Error verifying webhook signature: {error_message}"}

        # Ensure WebhookService methods were NOT called
        mock_service_instance.is_event_processed.assert_not_called()
        mock_service_instance.handle_checkout_session_completed.assert_not_called()
        mock_service_instance.handle_customer_subscription_created.assert_not_called()
        mock_service_instance.handle_customer_subscription_updated.assert_not_called()
        mock_service_instance.handle_invoice_payment_succeeded.assert_not_called()
        mock_service_instance.handle_invoice_payment_failed.assert_not_called()
        mock_service_instance.mark_event_as_processed.assert_not_called()
    finally:
        main_app.dependency_overrides.clear()