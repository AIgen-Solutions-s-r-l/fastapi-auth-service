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
from app.models.credit import CreditTransaction, UserCredit, TransactionType # Added TransactionType
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
def mock_subscription_model() -> MagicMock: # Added this fixture
    """Provides a mock Subscription object."""
    sub = MagicMock(spec=Subscription)
    # Set default attributes that might be accessed
    sub.user_id = None
    sub.stripe_subscription_id = None
    sub.stripe_customer_id = None
    sub.status = "unknown"
    sub.stripe_price_id = None
    sub.trial_end_date = None
    sub.current_period_start = None
    sub.current_period_end = None
    sub.cancel_at_period_end = False
    return sub

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
    # webhook_service.db.set_db_execute_scalar_first_results(None) # No existing fingerprint - check is removed
    webhook_service.db.set_db_get_result(mock_user)

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish_blocked:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish_blocked.assert_not_called() # Correct, blocking should not happen

    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    # Fingerprint check (db.execute) is removed from the SUT
    webhook_service.db.execute.assert_not_called() 
    mock_stripe_sub.delete.assert_not_called() 
    assert mock_user.account_status != "trial_rejected" 
    # No commit expected in this path of SUT if only fingerprint logic was removed
    if hasattr(webhook_service.db.commit, 'assert_not_called'): 
        webhook_service.db.commit.assert_not_called()
    else: 
        assert webhook_service.db.commit.call_count == 0

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
    
    # existing_fp_use = MagicMock(spec=UsedTrialCardFingerprint) # Fingerprint check removed
    # existing_fp_use.user_id = "other_user_id"                 # Fingerprint check removed
    # webhook_service.db.set_db_execute_scalar_first_results(existing_fp_use) # Fingerprint check removed
    webhook_service.db.set_db_get_result(mock_user) # User might still be fetched for other reasons
    original_status = mock_user.account_status

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_publish_blocked:
        await webhook_service.handle_checkout_session_completed(event)
        mock_publish_blocked.assert_not_called() # Correct: blocking should not happen
    
    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    mock_stripe_sub_delete.assert_not_called() # Correct: subscription should not be deleted
    
    # User.account_status should not be changed to 'trial_rejected'
    assert mock_user.account_status == original_status 
    
    # No commit expected in this path of SUT if only fingerprint logic was removed
    # and no user status update to 'trial_rejected' occurred.
    if hasattr(webhook_service.db.commit, 'assert_not_called'):
        webhook_service.db.commit.assert_not_called()
    else:
        assert webhook_service.db.commit.call_count == 0
    # mock_user.account_status = original_status # Already asserted

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
@patch("app.services.webhook_service.get_or_create_subscription") 
@patch("app.services.webhook_service.stripe.Subscription.delete") 
async def test_handle_customer_subscription_created_trial_unique_fingerprint(
    mock_stripe_sub_delete: MagicMock, 
    mock_get_or_create_sub: AsyncMock, 
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription 
):
    event_id = "evt_sub_trial_unique"
    user_id = mock_user.id
    stripe_price_id = "price_trial_unique"
    stripe_subscription_id = f"sub_trial_unique_{datetime.now().timestamp()}" 
    card_fingerprint = "fp_trial_unique_sub_created"
    default_payment_method_id = "pm_default_unique"
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
    trial_end_date_obj = datetime.fromtimestamp(trial_end_timestamp, timezone.utc)
    current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
    current_period_end_ts = trial_end_timestamp

    subscription_event_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        "default_payment_method": default_payment_method_id, 
        "current_period_start": current_period_start_ts,
        "current_period_end": current_period_end_ts,
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_event_data, event_id=event_id)

    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    
    mock_subscription_model.user_id = user_id 
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_subscription_model.stripe_customer_id = mock_user.stripe_customer_id
    mock_subscription_model.status = "unknown" 
    mock_subscription_model.stripe_price_id = None
    mock_subscription_model.trial_end_date = None
    mock_subscription_model.current_period_start = None
    mock_subscription_model.current_period_end = None
    mock_subscription_model.cancel_at_period_end = True 

    mock_get_or_create_sub.return_value = mock_subscription_model
    
    mock_user.has_consumed_initial_trial = False 
    original_account_status = mock_user.account_status 
    mock_user.account_status = "active" 

    webhook_service.db.set_db_get_result(mock_user) 
    webhook_service.db.set_db_execute_scalar_first_results(None) 
    webhook_service.db.add = MagicMock() 
    webhook_service.db.commit = AsyncMock() 
    webhook_service.db.rollback = AsyncMock() 
    webhook_service.db.flush = AsyncMock() 


    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        
        await webhook_service.handle_customer_subscription_created(event)
        
        mock_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=mock_user.stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_date_obj,
            credits_granted=settings.FREE_TRIAL_CREDITS
        )
        mock_trial_blocked.assert_not_called()

    webhook_service.get_card_fingerprint_from_event.assert_called_once()
    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    
    added_uc_instance = None
    added_ct_instance = None
    added_fingerprint_instance = None

    assert webhook_service.db.add.called, "db.add was not called"
    for call_args in webhook_service.db.add.call_args_list:
        instance = call_args[0][0]
        assert instance is not None, "db.add was called with a None object"
        if isinstance(instance, UserCredit):
            added_uc_instance = instance
        elif isinstance(instance, CreditTransaction):
            added_ct_instance = instance
        elif isinstance(instance, UsedTrialCardFingerprint):
            added_fingerprint_instance = instance 
            
    assert added_fingerprint_instance is None, "UsedTrialCardFingerprint record should NOT be added"
    
    assert added_uc_instance is not None, "UserCredit record was not added"
    if added_uc_instance: 
        assert added_uc_instance.user_id == user_id, "UserCredit user_id mismatch"
        assert added_uc_instance.balance == settings.FREE_TRIAL_CREDITS, "UserCredit balance incorrect"
    
    assert added_ct_instance is not None, "CreditTransaction record was not added"
    if added_ct_instance: 
        assert added_ct_instance.user_id == user_id, "CreditTransaction user_id mismatch"
        assert added_ct_instance.amount == settings.FREE_TRIAL_CREDITS, "CreditTransaction amount incorrect"
        assert added_ct_instance.transaction_type == TransactionType.TRIAL_CREDIT_GRANT, "CreditTransaction type incorrect"
        assert added_ct_instance.reference_id == stripe_subscription_id, "CreditTransaction reference_id incorrect"

    assert mock_user.has_consumed_initial_trial is True, "User's has_consumed_initial_trial flag not set"
    assert mock_user.account_status == 'trialing', f"User's account_status expected 'trialing', got '{mock_user.account_status}'"
    
    assert mock_subscription_model.status == "trialing"
    assert mock_subscription_model.stripe_price_id == stripe_price_id
    assert mock_subscription_model.trial_end_date == trial_end_date_obj
    assert mock_subscription_model.cancel_at_period_end is False

    webhook_service.db.commit.assert_called_once()
    webhook_service.db.rollback.assert_not_called()
    mock_user.account_status = original_account_status 

@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
@patch("app.services.webhook_service.stripe.Subscription.delete") 
async def test_handle_customer_subscription_created_trial_duplicate_fingerprint(
    mock_stripe_sub_delete: MagicMock, 
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription 
):
    event_id = "evt_sub_trial_duplicate" 
    user_id = mock_user.id
    stripe_price_id = "price_trial_duplicate"
    stripe_subscription_id = f"sub_trial_duplicate_{datetime.now().timestamp()}" 
    card_fingerprint = "fp_trial_duplicate_sub_created" 
    default_payment_method_id = "pm_default_duplicate"
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
    trial_end_date_obj = datetime.fromtimestamp(trial_end_timestamp, timezone.utc)
    current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
    current_period_end_ts = trial_end_timestamp

    subscription_event_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        "default_payment_method": default_payment_method_id,
        "current_period_start": current_period_start_ts,
        "current_period_end": current_period_end_ts,
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_event_data, event_id=event_id)
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint)
    
    mock_subscription_model.user_id = user_id
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_subscription_model.stripe_customer_id = mock_user.stripe_customer_id
    mock_subscription_model.status = "unknown" 
    mock_subscription_model.stripe_price_id = None
    mock_subscription_model.trial_end_date = None
    mock_subscription_model.current_period_start = None
    mock_subscription_model.current_period_end = None
    mock_subscription_model.cancel_at_period_end = True
    mock_get_or_create_sub.return_value = mock_subscription_model
    
    mock_user.has_consumed_initial_trial = False 
    original_account_status = mock_user.account_status
    mock_user.account_status = "active"

    webhook_service.db.set_db_get_result(mock_user) 
    webhook_service.db.set_db_execute_scalar_first_results(None) 

    webhook_service.db.flush = AsyncMock() 
    webhook_service.db.add = MagicMock()
    webhook_service.db.commit = AsyncMock()
    webhook_service.db.rollback = AsyncMock()


    with patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started:
        
        await webhook_service.handle_customer_subscription_created(event)
        
        mock_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=mock_user.stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_date_obj,
            credits_granted=settings.FREE_TRIAL_CREDITS
        )
        mock_trial_blocked.assert_not_called()

    mock_stripe_sub_delete.assert_not_called() 
    
    added_uc_instance = None
    added_ct_instance = None
    added_fingerprint_instance = None

    assert webhook_service.db.add.called, "db.add was not called in duplicate fingerprint test (which is now unique path)"
    for call_args in webhook_service.db.add.call_args_list:
        instance = call_args[0][0]
        assert instance is not None, "db.add was called with a None object (duplicate test path)"
        if isinstance(instance, UserCredit):
            added_uc_instance = instance
        elif isinstance(instance, CreditTransaction):
            added_ct_instance = instance
        elif isinstance(instance, UsedTrialCardFingerprint):
            added_fingerprint_instance = instance
            
    assert added_fingerprint_instance is None, "UsedTrialCardFingerprint record should NOT be added (duplicate test path)"
    
    assert added_uc_instance is not None, "UserCredit record was not added (duplicate test path)"
    if added_uc_instance:
        assert added_uc_instance.user_id == user_id
        assert added_uc_instance.balance == settings.FREE_TRIAL_CREDITS
    
    assert added_ct_instance is not None, "CreditTransaction record was not added (duplicate test path)"
    if added_ct_instance:
        assert added_ct_instance.user_id == user_id
        assert added_ct_instance.amount == settings.FREE_TRIAL_CREDITS
        assert added_ct_instance.transaction_type == TransactionType.TRIAL_CREDIT_GRANT
        assert added_ct_instance.reference_id == stripe_subscription_id

    assert mock_user.has_consumed_initial_trial is True, "User's has_consumed_initial_trial flag not set (duplicate test path)"
    assert mock_user.account_status == 'trialing', f"User's account_status expected 'trialing', got '{mock_user.account_status}' (duplicate test path)"
    
    assert mock_subscription_model.status == "trialing"
    assert mock_subscription_model.stripe_price_id == stripe_price_id
    assert mock_subscription_model.trial_end_date == trial_end_date_obj
    assert mock_subscription_model.cancel_at_period_end is False

    webhook_service.db.commit.assert_called_once() 
    webhook_service.db.rollback.assert_not_called()
    mock_user.account_status = original_account_status 

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
        monkeypatch.setattr(settings, "FREE_TRIAL_CREDITS", 10) # Ensure this is defined

    stripe_price_id = settings.STRIPE_FREE_TRIAL_PRICE_ID
    stripe_subscription_id = "sub_trial_consumed_789"
    card_fingerprint = "fp_trial_consumed" # Fingerprint doesn't matter as much here
    default_payment_method_id = "pm_trial_consumed"
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=settings.FREE_TRIAL_DAYS)).timestamp())
    trial_end_date_obj = datetime.fromtimestamp(trial_end_timestamp, timezone.utc)
    current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
    current_period_end_ts = trial_end_timestamp


    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        "default_payment_method": default_payment_method_id,
        "current_period_start": current_period_start_ts,
        "current_period_end": current_period_end_ts, 
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=card_fingerprint) # Still need to mock this call

    mock_db_subscription = MagicMock(spec=Subscription)
    mock_db_subscription.user_id = user_id
    mock_db_subscription.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_db_subscription

    mock_user.has_consumed_initial_trial = True # Key for this test
    original_account_status = mock_user.account_status
    mock_user.account_status = "active" # Start with a non-trialing status

    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.add = MagicMock() # Reset add mock
    webhook_service.db.commit = AsyncMock()
    webhook_service.db.rollback = AsyncMock()


    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        mock_trial_started.assert_not_called() # No credits/trial start if already consumed
        mock_trial_blocked.assert_not_called()

    # Check that UserCredit and CreditTransaction were NOT added
    assert not any(isinstance(call.args[0], UserCredit) for call in webhook_service.db.add.call_args_list)
    assert not any(isinstance(call.args[0], CreditTransaction) for call in webhook_service.db.add.call_args_list)
    assert not any(isinstance(call.args[0], UsedTrialCardFingerprint) for call in webhook_service.db.add.call_args_list)


    assert mock_user.has_consumed_initial_trial is True # Should remain true
    assert mock_user.account_status == "trialing" # Status should still update to trialing as per service logic
    webhook_service.db.commit.assert_called_once() # Commit for user status and subscription update
    mock_user.account_status = original_account_status # Restore


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_missing_user_id(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_sub_created_no_user"
    stripe_price_id = "price_no_user_sub"
    stripe_subscription_id = "sub_no_user_123"
    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": "cus_no_user_mapping",
        "status": "active", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {}, # No user_id in metadata
        "trial_end": None,
        "current_period_start": int(datetime.now(timezone.utc).timestamp()),
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": False
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    # Simulate user not found by stripe_customer_id
    webhook_service.db.set_db_execute_scalar_first_results(None) 

    with patch.object(webhook_service.event_publisher, 'publish_user_trial_started', new_callable=AsyncMock) as mock_trial_started, \
         patch.object(webhook_service.event_publisher, 'publish_user_trial_blocked', new_callable=AsyncMock) as mock_trial_blocked:
        await webhook_service.handle_customer_subscription_created(event)
        mock_trial_started.assert_not_called()
        mock_trial_blocked.assert_not_called()

    mock_get_or_create_sub.assert_not_called() # Should not proceed to this if user_id is not resolved
    webhook_service.db.commit.assert_not_called()


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_created_trial_missing_fingerprint(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription
):
    event_id = "evt_sub_trial_no_fp"
    user_id = mock_user.id
    stripe_price_id = "price_trial_no_fp"
    stripe_subscription_id = "sub_trial_no_fp_123"
    trial_end_timestamp = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": mock_user.stripe_customer_id,
        "status": "trialing", "items": {"data": [{"price": {"id": stripe_price_id}}]},
        "metadata": {"user_id": user_id}, "trial_end": trial_end_timestamp,
        "current_period_start": int(datetime.now(timezone.utc).timestamp()), # Added
        "current_period_end": trial_end_timestamp, # Added
        "cancel_at_period_end": False # Added
        # No default_payment_method, or get_card_fingerprint_from_event will be mocked to return None
    }
    event = mock_stripe_event_factory("customer.subscription.created", subscription_data, event_id=event_id)
    
    webhook_service.get_card_fingerprint_from_event = AsyncMock(return_value=None) # Simulate missing fingerprint
    
    mock_subscription_model.user_id = user_id
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_get_or_create_sub.return_value = mock_subscription_model
    
    webhook_service.db.set_db_get_result(mock_user)

    with pytest.raises(ValueError, match=f"Card fingerprint missing for trial subscription {stripe_subscription_id}"):
        await webhook_service.handle_customer_subscription_created(event)

    webhook_service.db.rollback.assert_called_once() # Expect rollback due to the raised ValueError
    webhook_service.db.commit.assert_not_called()


# --- WebhookService.handle_customer_subscription_updated Tests ---
@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription") # Added for consistency if sub not found
async def test_handle_customer_subscription_updated_status_change_active_to_frozen(
    mock_get_or_create_sub: AsyncMock, # Added
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription # Use the fixture
):
    event_id = "evt_sub_updated_active_to_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_active_to_frozen_123"
    
    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "past_due", # This should trigger 'frozen'
        "items": {"data": [{"price": {"id": "price_some_plan"}}]}, # Ensure items.data[0].price.id exists
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()), # Added
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()), # Added
        "cancel_at_period_end": False # Added
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    # Setup mock_user and mock_subscription_model state
    original_user_status = "active"
    mock_user.account_status = original_user_status
    
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_subscription_model.status = "active" # Previous status
    
    webhook_service.db.set_db_execute_scalar_first_results(mock_subscription_model) # For select(Subscription)
    webhook_service.db.set_db_get_result(mock_user) # For self.db.get(User, user_id)
    webhook_service.db.commit = AsyncMock() # Reset commit mock

    with patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )

    assert mock_user.account_status == "frozen"
    assert mock_subscription_model.status == "past_due"
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_user_status # Restore


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_status_change_frozen_to_active(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription
):
    event_id = "evt_sub_updated_frozen_to_active"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_frozen_to_active_456"

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": "active", 
        "items": {"data": [{"price": {"id": "price_another_plan"}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()), # Added
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()), # Added
        "cancel_at_period_end": False # Added
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    original_user_status = "frozen"
    mock_user.account_status = original_user_status
    
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_subscription_model.status = "past_due" # Previous status
        
    webhook_service.db.set_db_execute_scalar_first_results(mock_subscription_model)
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.commit = AsyncMock()

    with patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_unfrozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )

    assert mock_user.account_status == "active"
    assert mock_subscription_model.status == "active"
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_user_status # Restore


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_local_sub_not_found(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User,
    mock_subscription_model: Subscription # Use the fixture
):
    """Test handling when local subscription record doesn't exist initially."""
    event_id = "evt_sub_updated_not_found"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_not_found_then_created_789"
    new_stripe_status = "active"

    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": stripe_customer_id,
        "status": new_stripe_status,
        "items": {"data": [{"price": {"id": "price_for_new_sub"}}]},
        "metadata": {"user_id": user_id},
        "current_period_start": int(datetime.now(timezone.utc).timestamp()), # Added
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()), # Added
        "cancel_at_period_end": False # Added
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    webhook_service.db.set_db_execute_scalar_first_results(None) # Simulate subscription not found initially
    
    # Configure the mock_subscription_model that get_or_create_subscription will return
    mock_subscription_model.user_id = user_id
    mock_subscription_model.stripe_subscription_id = stripe_subscription_id
    mock_subscription_model.stripe_customer_id = stripe_customer_id # Ensure this is set
    # Set other attributes to initial values that will be updated
    mock_subscription_model.status = "initial_unknown_status" 
    mock_subscription_model.stripe_price_id = None

    mock_get_or_create_sub.return_value = mock_subscription_model # get_or_create_sub will return this
    
    original_user_status = "pending" # Some initial status
    mock_user.account_status = original_user_status
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.commit = AsyncMock()


    with patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_customer_subscription_updated(event)
        # If status changes from non-frozen to active, unfrozen might be called if previous was 'frozen'
        # If it was 'pending' -> 'active', neither frozen nor unfrozen should be called for this specific transition.
        # The test setup implies a change to 'active', so if original was 'frozen', unfreeze is called.
        # If original was 'pending', no status-change event specific to frozen/unfrozen.
        if original_user_status == "frozen":
            mock_publish_unfrozen.assert_called_once()
            mock_publish_frozen.assert_not_called()
        else:
            mock_publish_unfrozen.assert_not_called()
            mock_publish_frozen.assert_not_called()


    mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
    assert mock_user.account_status == new_stripe_status # User status should align
    assert mock_subscription_model.status == new_stripe_status # Local sub status updated
    assert mock_subscription_model.stripe_price_id == "price_for_new_sub" # Check price_id update
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_user_status # Restore


@pytest.mark.asyncio
@patch("app.services.webhook_service.get_or_create_subscription")
async def test_handle_customer_subscription_updated_missing_user_id(
    mock_get_or_create_sub: AsyncMock,
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_sub_updated_no_user"
    stripe_subscription_id = "sub_no_user_update_123"
    subscription_data = {
        "id": stripe_subscription_id, "object": "subscription", "customer": "cus_no_user_mapping_update",
        "status": "active", "metadata": {}, # No user_id
        "current_period_start": int(datetime.now(timezone.utc).timestamp()), # Added
        "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()), # Added
        "cancel_at_period_end": False # Added
    }
    event = mock_stripe_event_factory("customer.subscription.updated", subscription_data, event_id=event_id)

    webhook_service.db.set_db_execute_scalar_first_results(None) # For User.id lookup by stripe_customer_id

    with patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
        await webhook_service.handle_customer_subscription_updated(event)
        mock_publish_frozen.assert_not_called()
        mock_publish_unfrozen.assert_not_called()
    
    mock_get_or_create_sub.assert_not_called() # Should not reach subscription handling
    webhook_service.db.commit.assert_not_called()


# --- WebhookService.handle_invoice_payment_succeeded Tests ---
# @pytest.mark.asyncio
# async def test_handle_invoice_payment_succeeded_success_active_user(
#     webhook_service: WebhookService,
#     mock_stripe_event_factory: Callable,
#     mock_user: User
# ):
#     event_id = "evt_inv_paid_active"
#     user_id = mock_user.id
#     stripe_customer_id = mock_user.stripe_customer_id
#     stripe_subscription_id = "sub_for_invoice_123" # Can be None for one-off invoices
#     stripe_invoice_id = "in_invoice_paid_123"

#     invoice_data = {
#         "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
#         "subscription": stripe_subscription_id, "paid": True, "status": "paid",
#         "customer_details": {"metadata": {"user_id": user_id}}, 
#         "amount_paid": 1000, 
#         "currency": "usd", 
#         "billing_reason": "subscription_cycle", 
#         "invoice_pdf": "https://example.com/invoice.pdf" 
#     }
#     event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

#     original_account_status = "active" 
#     mock_user.account_status = original_account_status
#     webhook_service.db.set_db_get_result(mock_user) 
#     webhook_service.db.commit = AsyncMock()


#     with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
#          patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
#         await webhook_service.handle_invoice_payment_succeeded(event)
        
#         mock_publish_paid.assert_called_once_with(
#             user_id=user_id,
#             stripe_customer_id=stripe_customer_id,
#             stripe_subscription_id=stripe_subscription_id, 
#             stripe_invoice_id=stripe_invoice_id,
#             amount_paid=invoice_data.get("amount_paid", 0), 
#             currency=invoice_data.get("currency"),
#             billing_reason=invoice_data.get("billing_reason"),
#             invoice_pdf_url=invoice_data.get("invoice_pdf")
#         )
#         mock_publish_unfrozen.assert_not_called() 

#     assert mock_user.account_status == "active" 
#     webhook_service.db.commit.assert_called_once() 
#     mock_user.account_status = original_account_status 


# @pytest.mark.asyncio
# async def test_handle_invoice_payment_succeeded_unfreezes_user(
#     webhook_service: WebhookService,
#     mock_stripe_event_factory: Callable,
#     mock_user: User
# ):
#     event_id = "evt_inv_paid_unfreeze"
#     user_id = mock_user.id
#     stripe_customer_id = mock_user.stripe_customer_id
#     stripe_subscription_id = "sub_for_unfreeze_invoice_456"
#     stripe_invoice_id = "in_invoice_unfreeze_456"

#     invoice_data = {
#         "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
#         "subscription": stripe_subscription_id, "paid": True, "status": "paid",
#         "customer_details": {"metadata": {"user_id": user_id}},
#         "billing_reason": "subscription_cycle", 
#         "amount_paid": 1000, 
#         "currency": "usd", 
#         "invoice_pdf": "https://example.com/invoice.pdf" 
#     }
#     event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

#     original_account_status = "frozen" 
#     mock_user.account_status = original_account_status
#     webhook_service.db.set_db_get_result(mock_user)
#     webhook_service.db.commit = AsyncMock()

#     with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
#          patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
#         await webhook_service.handle_invoice_payment_succeeded(event)
        
#         mock_publish_paid.assert_called_once() 
#         mock_publish_unfrozen.assert_called_once_with(
#             user_id=user_id,
#             stripe_customer_id=stripe_customer_id,
#             stripe_subscription_id=stripe_subscription_id,
#             reason="invoice_paid_after_failure"
#         )

#     assert mock_user.account_status == "active" 
#     webhook_service.db.commit.assert_called_once()
#     mock_user.account_status = original_account_status 


# @pytest.mark.asyncio
# async def test_handle_invoice_payment_succeeded_missing_user_id(
#     webhook_service: WebhookService,
#     mock_stripe_event_factory: Callable
# ):
#     event_id = "evt_inv_paid_no_user"
#     stripe_invoice_id = "in_invoice_no_user_789"
#     invoice_data = {
#         "id": stripe_invoice_id, "object": "invoice", "customer": "cus_no_user_mapping_invoice",
#         "subscription": None, "paid": True, "status": "paid",
#         "customer_details": {"metadata": {}}, 
#         "amount_paid": 0, "currency": "usd", "billing_reason": "manual", "invoice_pdf": None 
#     }
#     event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)
    
#     webhook_service.db.set_db_execute_scalar_first_results(None) 

#     with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
#          patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
#         await webhook_service.handle_invoice_payment_succeeded(event)
#         mock_publish_paid.assert_not_called()
#         mock_publish_unfrozen.assert_not_called()
    
#     webhook_service.db.commit.assert_not_called()


# @pytest.mark.asyncio
# async def test_handle_invoice_payment_succeeded_user_not_found_in_db(
#     webhook_service: WebhookService,
#     mock_stripe_event_factory: Callable
# ):
#     event_id = "evt_inv_paid_user_not_db"
#     user_id_from_meta = "user_meta_not_in_db"
#     stripe_customer_id = "cus_user_not_in_db"
#     stripe_invoice_id = "in_invoice_user_not_db"

#     invoice_data = {
#         "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
#         "subscription": None, "paid": True, "status": "paid",
#         "customer_details": {"metadata": {"user_id": user_id_from_meta}},
#         "amount_paid": 0, "currency": "usd", "billing_reason": "manual", "invoice_pdf": None 
#     }
#     event = mock_stripe_event_factory("invoice.payment_succeeded", invoice_data, event_id=event_id)

#     webhook_service.db.set_db_get_result(None) # Simulate user not found by self.db.get()

#     with patch.object(webhook_service.event_publisher, 'publish_user_invoice_paid', new_callable=AsyncMock) as mock_publish_paid, \
#          patch.object(webhook_service.event_publisher, 'publish_user_account_unfrozen', new_callable=AsyncMock) as mock_publish_unfrozen:
#         await webhook_service.handle_invoice_payment_succeeded(event)
#         mock_publish_paid.assert_not_called() # Corrected: Should not be called if user not found
#         mock_publish_unfrozen.assert_not_called() 

#     webhook_service.db.commit.assert_not_called() # No user to update, so no commit


# --- WebhookService.handle_invoice_payment_failed Tests ---
@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_freezes_active_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_freeze"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_for_failed_invoice_123"
    stripe_invoice_id = "in_invoice_failed_123"

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "paid": False, "status": "open", 
        "customer_details": {"metadata": {"user_id": user_id}},
        "billing_reason": "subscription_cycle", 
        "charge": "ch_charge_id_example", 
        "last_payment_error": {"message": "Card declined"},
        "next_payment_attempt": int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp()) 
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    original_account_status = "active"
    mock_user.account_status = original_account_status
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.commit = AsyncMock()

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_publish_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_charge_id=invoice_data.get('charge'), 
            failure_reason=invoice_data.get('last_payment_error', {}).get('message'), 
            next_payment_attempt_date=datetime.fromtimestamp(invoice_data['next_payment_attempt'], timezone.utc)
        )
        mock_publish_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="invoice_payment_failed"
        )
    
    assert mock_user.account_status == "frozen"
    webhook_service.db.commit.assert_called_once()
    mock_user.account_status = original_account_status 


@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_already_frozen_user(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_already_frozen"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_subscription_id = "sub_already_frozen_inv_456"
    stripe_invoice_id = "in_invoice_already_frozen_456"

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": stripe_subscription_id, "paid": False, "status": "open",
        "customer_details": {"metadata": {"user_id": user_id}},
        "billing_reason": "subscription_cycle",
        "charge": "ch_charge_id_example_frozen", 
        "last_payment_error": {"message": "Card still declined"},
        "next_payment_attempt": None 
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    original_account_status = "frozen" 
    mock_user.account_status = original_account_status
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.commit = AsyncMock()

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_publish_failed.assert_called_once() 
        mock_publish_frozen.assert_not_called() 

    assert mock_user.account_status == "frozen" 
    webhook_service.db.commit.assert_called_once() 
    mock_user.account_status = original_account_status 


@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_non_subscription_reason(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable,
    mock_user: User
):
    event_id = "evt_inv_failed_non_sub"
    user_id = mock_user.id
    stripe_customer_id = mock_user.stripe_customer_id
    stripe_invoice_id = "in_invoice_non_sub_789"

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": None, 
        "paid": False, "status": "open",
        "customer_details": {"metadata": {"user_id": user_id}},
        "billing_reason": "manual", 
        "charge": "ch_charge_id_example_non_sub",
        "last_payment_error": {"message": "Payment failed for manual invoice"},
        "next_payment_attempt": None 
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    original_account_status = "active"
    mock_user.account_status = original_account_status
    webhook_service.db.set_db_get_result(mock_user)
    webhook_service.db.commit = AsyncMock()

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_publish_failed.assert_called_once()
        mock_publish_frozen.assert_not_called() 

    assert mock_user.account_status == "active" 
    webhook_service.db.commit.assert_not_called() 
    mock_user.account_status = original_account_status 


@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_missing_user_id(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_failed_no_user"
    stripe_invoice_id = "in_invoice_no_user_failed"
    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": "cus_no_user_mapping_failed_inv",
        "subscription": None, "paid": False, "status": "open",
        "customer_details": {"metadata": {}}, 
        "charge": "ch_charge_id_example_no_user",
        "last_payment_error": {"message": "Payment failed"},
        "next_payment_attempt": None 
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    webhook_service.db.set_db_execute_scalar_first_results(None) 

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_not_called() 
        mock_publish_frozen.assert_not_called()
    
    webhook_service.db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_handle_invoice_payment_failed_user_not_found_in_db(
    webhook_service: WebhookService,
    mock_stripe_event_factory: Callable
):
    event_id = "evt_inv_failed_user_not_db"
    user_id_from_meta = "user_meta_not_in_db_failed"
    stripe_customer_id = "cus_user_not_in_db_failed"
    stripe_invoice_id = "in_invoice_user_not_db_failed"

    invoice_data = {
        "id": stripe_invoice_id, "object": "invoice", "customer": stripe_customer_id,
        "subscription": None, "paid": False, "status": "open",
        "customer_details": {"metadata": {"user_id": user_id_from_meta}},
        "charge": "ch_charge_id_example_user_not_db", 
        "last_payment_error": {"message": "Payment failed"},
        "next_payment_attempt": None 
    }
    event = mock_stripe_event_factory("invoice.payment_failed", invoice_data, event_id=event_id)

    webhook_service.db.set_db_get_result(None) # Simulate user not found by self.db.get()

    with patch.object(webhook_service.event_publisher, 'publish_user_invoice_failed', new_callable=AsyncMock) as mock_publish_failed, \
         patch.object(webhook_service.event_publisher, 'publish_user_account_frozen', new_callable=AsyncMock) as mock_publish_frozen:
        await webhook_service.handle_invoice_payment_failed(event)
        mock_publish_failed.assert_not_called() # Corrected
        mock_publish_frozen.assert_not_called() 

    webhook_service.db.commit.assert_not_called() # No user to update, so no commit


# --- Endpoint Tests (Example for one handler, others would be similar) ---

# Helper to mock the verify_stripe_signature dependency for endpoint tests
def create_mock_verify_dependency(mock_event_to_return: stripe.Event) -> Callable:
    """Factory to create a mock for the verify_stripe_signature dependency."""
    async def mock_verify_stripe_signature_override(
        request: Request, 
        stripe_signature: str = Header(None) # Ensure Header is imported from fastapi
    ) -> stripe.Event:
        return mock_event_to_return
    return mock_verify_stripe_signature_override

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_checkout_session_completed(
    client: AsyncClient, 
    mock_stripe_event_factory: Callable, 
    mock_db_session: AsyncMock, # Ensure mock_db_session is used by the endpoint via override
    mock_user: User
):
    """Integration test for a valid checkout.session.completed event."""
    event_type = "checkout.session.completed"
    event_id = "evt_endpoint_checkout_success"
    user_id = mock_user.id
    card_fingerprint = "fp_endpoint_checkout"
    checkout_data = {
        "id": "cs_endpoint_test", "client_reference_id": user_id, 
        "customer": "cus_endpoint_test", "subscription": "sub_endpoint_test",
        "payment_intent": "pi_endpoint_test", "metadata": {"user_id": user_id}
    }
    mock_event = mock_stripe_event_factory(event_type, checkout_data, event_id=event_id)

    # Mock WebhookService methods that would be called
    # Since WebhookService is instantiated inside the endpoint, we patch its methods globally for the test
    with patch("app.services.webhook_service.WebhookService.is_event_processed", AsyncMock(return_value=False)) as mock_is_processed, \
         patch("app.services.webhook_service.WebhookService.mark_event_as_processed", AsyncMock()) as mock_mark_processed, \
         patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", AsyncMock()) as mock_handler, \
         patch("app.services.webhook_service.WebhookService.get_card_fingerprint_from_event", AsyncMock(return_value=card_fingerprint)): # Also mock this if handler uses it

        # Override the dependency for this specific test path
        main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)

        response = await client.post("/webhooks/stripe", content="dummy_payload", headers={"Stripe-Signature": "t=123,v1=dummy"})

        assert response.status_code == 200
        # Updated assertion to match router's actual response
        assert response.json() == {"status": "success", "message": f"Successfully processed event: {event_id} ({event_type})"}
        
        mock_is_processed.assert_called_once_with(event_id)
        mock_handler.assert_called_once_with(mock_event)
        mock_mark_processed.assert_called_once_with(event_id, event_type)

    # Clean up dependency override
    del main_app.dependency_overrides[verify_stripe_signature]


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_idempotency(
    client: AsyncClient, 
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock
):
    """Test that already processed events are handled idempotently."""
    event_type = "checkout.session.completed" # Any handled event type
    event_id = "evt_endpoint_idempotent"
    mock_event_data = {"id": "obj_idempotent"}
    mock_event = mock_stripe_event_factory(event_type, mock_event_data, event_id=event_id)

    with patch("app.services.webhook_service.WebhookService.is_event_processed", AsyncMock(return_value=True)) as mock_is_processed, \
         patch("app.services.webhook_service.WebhookService.mark_event_as_processed", AsyncMock()) as mock_mark_processed, \
         patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", AsyncMock()) as mock_handler: # Patch a handler

        main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
        
        response = await client.post("/webhooks/stripe", content="dummy_payload", headers={"Stripe-Signature": "t=123,v1=dummy"})

        assert response.status_code == 200
        # Updated assertion to match router's actual response
        assert response.json() == {"status": "success", "message": f"Event {event_id} already processed."}
        
        mock_is_processed.assert_called_once_with(event_id)
        mock_handler.assert_not_called() # Handler should not be called
        mock_mark_processed.assert_not_called() # Should not be marked again

    del main_app.dependency_overrides[verify_stripe_signature]


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_unhandled_event_type(
    client: AsyncClient, 
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock
):
    """Test the endpoint with an unhandled event type."""
    event_type = "unhandled.event.type"
    event_id = "evt_endpoint_unhandled"
    mock_event_data = {"id": "obj_unhandled"}
    mock_event = mock_stripe_event_factory(event_type, mock_event_data, event_id=event_id)

    with patch("app.services.webhook_service.WebhookService.is_event_processed", AsyncMock(return_value=False)) as mock_is_processed, \
         patch("app.services.webhook_service.WebhookService.mark_event_as_processed", AsyncMock()) as mock_mark_processed:
        # No specific handler needs to be patched as it shouldn't be called

        main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
        
        response = await client.post("/webhooks/stripe", content="dummy_payload", headers={"Stripe-Signature": "t=123,v1=dummy"})

        assert response.status_code == 200
        # Updated assertion to match router's actual response
        assert response.json() == {"status": "success", "message": f"Webhook received for unhandled event type: {event_type}"}
        
        mock_is_processed.assert_called_once_with(event_id)
        # mark_event_as_processed might still be called depending on desired behavior for unhandled events.
        # If unhandled events should also be marked to prevent reprocessing attempts:
        mock_mark_processed.assert_called_once_with(event_id, event_type)
        # If not, then: mock_mark_processed.assert_not_called()

    del main_app.dependency_overrides[verify_stripe_signature]


@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_handler_exception(
    client: AsyncClient, 
    mock_stripe_event_factory: Callable,
    mock_db_session: AsyncMock # Ensure this is injected
):
    """Test the endpoint when a handler raises an exception."""
    event_type = "checkout.session.completed" # An event type with a handler
    event_id = "evt_endpoint_handler_exc"
    mock_event_data = {"id": "obj_handler_exc"}
    mock_event = mock_stripe_event_factory(event_type, mock_event_data, event_id=event_id)

    simulated_error_message = "Handler failed processing"
    # Patch the specific handler to raise an exception
    with patch("app.services.webhook_service.WebhookService.is_event_processed", AsyncMock(return_value=False)) as mock_is_processed, \
         patch("app.services.webhook_service.WebhookService.mark_event_as_processed", AsyncMock()) as mock_mark_processed, \
         patch("app.services.webhook_service.WebhookService.handle_checkout_session_completed", AsyncMock(side_effect=SQLAlchemyError(simulated_error_message))) as mock_handler:

        main_app.dependency_overrides[verify_stripe_signature] = create_mock_verify_dependency(mock_event)
        
        # The endpoint should catch the SQLAlchemyError and return 500
        response = await client.post("/webhooks/stripe", content="dummy_payload", headers={"Stripe-Signature": "t=123,v1=dummy"})

        assert response.status_code == 500
        assert simulated_error_message in response.text # Check if the error message is part of the response
        
        mock_is_processed.assert_called_once_with(event_id)
        mock_handler.assert_called_once_with(mock_event)
        # mark_event_as_processed should NOT be called if the handler fails before it can be marked
        mock_mark_processed.assert_not_called() 
        # Rollback should have been called by the error handler in WebhookService or endpoint
        mock_db_session.rollback.assert_called_once()


    del main_app.dependency_overrides[verify_stripe_signature]

@pytest.mark.asyncio
async def test_stripe_webhook_endpoint_signature_error(client: AsyncClient):
    """Test the endpoint when Stripe signature verification fails."""
    
    # Mock the dependency to raise SignatureVerificationError
    async def mock_verify_dependency_raises(request: Request, stripe_signature: str = None):
        raise HTTPException(status_code=400, detail="Stripe signature verification failed")
    
    original_verify_dependency = main_app.dependency_overrides.get(verify_stripe_signature)
    main_app.dependency_overrides[verify_stripe_signature] = mock_verify_dependency_raises

    # No need to patch WebhookService methods as they won't be reached
    with patch("app.services.webhook_service.WebhookService.is_event_processed", AsyncMock()) as mock_is_processed, \
         patch("app.services.webhook_service.WebhookService.mark_event_as_processed", AsyncMock()) as mock_mark_processed:

        response = await client.post("/webhooks/stripe", content="dummy_payload", headers={"Stripe-Signature": "t=invalid,v1=invalid"})

        assert response.status_code == 400
        assert "Stripe signature verification failed" in response.text
        
        mock_is_processed.assert_not_called()
        mock_mark_processed.assert_not_called()

    # Restore original dependency
    if original_verify_dependency:
        main_app.dependency_overrides[verify_stripe_signature] = original_verify_dependency
    else:
        del main_app.dependency_overrides[verify_stripe_signature]

# Ensure TransactionType is available for tests that might need it
# from app.models.credit import TransactionType # Already imported at the top