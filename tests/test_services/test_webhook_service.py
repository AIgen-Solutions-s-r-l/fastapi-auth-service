import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Optional, Dict, Any
from datetime import datetime, timezone

import stripe # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.webhook_service import WebhookService
from app.models.user import User
from app.models.plan import UsedTrialCardFingerprint, Subscription
from app.models.processed_event import ProcessedStripeEvent
from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.services.internal_event_publisher import InternalEventPublisher
from app.core.config import settings # For stripe.api_key if needed directly in tests, though usually mocked

# --- Fixtures ---

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.scalars = AsyncMock()
    session.scalar = AsyncMock()
    session.first = AsyncMock()
    session.get = AsyncMock()
    session.merge = AsyncMock()
    session.add = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session

@pytest.fixture
def mock_event_publisher() -> MagicMock:
    """Provides a mock InternalEventPublisher."""
    publisher = MagicMock(spec=InternalEventPublisher)
    publisher.publish_user_trial_blocked = AsyncMock()
    publisher.publish_user_trial_started = AsyncMock()
    publisher.publish_user_account_frozen = AsyncMock()
    publisher.publish_user_account_unfrozen = AsyncMock()
    publisher.publish_user_invoice_paid = AsyncMock()
    publisher.publish_user_invoice_failed = AsyncMock()
    return publisher

@pytest.fixture
def mock_stripe_event() -> MagicMock:
    """Provides a generic mock Stripe Event object."""
    event = MagicMock(spec=stripe.Event)
    event.id = "evt_test_event_id"
    event.type = "test.event"
    event.data = MagicMock()
    event.data.object = MagicMock()
    return event

@pytest.fixture
def mock_logger() -> MagicMock:
    """Provides a mock logger."""
    return MagicMock()

@pytest.fixture
@patch('app.services.webhook_service.InternalEventPublisher')
def webhook_service(
    mock_internal_event_publisher_class: MagicMock,
    mock_db_session: AsyncMock,
    mock_event_publisher: MagicMock
) -> WebhookService:
    """Provides an instance of WebhookService with mocked dependencies."""
    mock_internal_event_publisher_class.return_value = mock_event_publisher
    service = WebhookService(db_session=mock_db_session)
    return service

# --- Helper Functions for Creating Stripe Event Payloads ---

def create_stripe_event_payload(
    event_id: str = "evt_test_generic",
    event_type: str = "checkout.session.completed",
    data_object: Optional[Dict[str, Any]] = None
) -> MagicMock:
    event = MagicMock(spec=stripe.Event)
    event.id = event_id
    event.type = event_type
    event.data = MagicMock()
    if data_object is None:
        data_object = {}
    
    # Convert dict to MagicMock recursively for nested objects
    def dict_to_magicmock(d):
        if isinstance(d, dict):
            m = MagicMock()
            for k, v in d.items():
                setattr(m, k, dict_to_magicmock(v))
            return m
        elif isinstance(d, list):
            return [dict_to_magicmock(item) for item in d]
        return d

    event.data.object = dict_to_magicmock(data_object)
    return event

# --- Test Classes ---

@pytest.mark.asyncio
class TestWebhookServiceEventProcessing:
    """Tests for event processing checks (is_event_processed, mark_event_as_processed)."""

    async def test_is_event_processed_returns_true_if_exists(self, webhook_service: WebhookService, mock_db_session: AsyncMock):
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = ProcessedStripeEvent(stripe_event_id="evt_exists")
        assert await webhook_service.is_event_processed("evt_exists") is True
        mock_db_session.execute.assert_called_once()

    async def test_is_event_processed_returns_false_if_not_exists(self, webhook_service: WebhookService, mock_db_session: AsyncMock):
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None
        assert await webhook_service.is_event_processed("evt_not_exists") is False

    async def test_mark_event_as_processed_success(self, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_id = "evt_to_mark"
        event_type = "test.processing"
        
        # Mock the pg_insert chain
        mock_insert_stmt = MagicMock()
        mock_on_conflict = MagicMock()
        
        with patch('app.services.webhook_service.pg_insert', return_value=mock_insert_stmt) as mock_pg_insert_fn:
            mock_insert_stmt.values.return_value.on_conflict_do_nothing.return_value = mock_on_conflict
            
            await webhook_service.mark_event_as_processed(event_id, event_type)

            mock_pg_insert_fn.assert_called_once_with(ProcessedStripeEvent)
            mock_insert_stmt.values.assert_called_once_with(stripe_event_id=event_id, event_type=event_type)
            mock_insert_stmt.values.return_value.on_conflict_do_nothing.assert_called_once_with(index_elements=['stripe_event_id'])
            mock_db_session.execute.assert_called_once_with(mock_on_conflict)
            mock_db_session.commit.assert_called_once()
            mock_db_session.rollback.assert_not_called()

    async def test_mark_event_as_processed_sqlalchemy_error_rolls_back_and_raises(self, webhook_service: WebhookService, mock_db_session: AsyncMock):
        mock_db_session.execute.side_effect = SQLAlchemyError("DB boom")
        with pytest.raises(SQLAlchemyError):
            await webhook_service.mark_event_as_processed("evt_err", "test.error")
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()


@pytest.mark.asyncio
class TestWebhookServiceGetCardFingerprint:
    """Tests for get_card_fingerprint_from_event."""

    @patch('app.services.webhook_service.stripe.PaymentIntent')
    async def test_get_fingerprint_from_payment_intent(self, mock_stripe_payment_intent: MagicMock, webhook_service: WebhookService):
        mock_pi = MagicMock()
        mock_pi.payment_method = MagicMock()
        mock_pi.payment_method.card = MagicMock()
        mock_pi.payment_method.card.fingerprint = "fingerprint_from_pi"
        mock_stripe_payment_intent.retrieve.return_value = mock_pi

        event_data = MagicMock()
        event_data.get = MagicMock(side_effect=lambda key: "pi_123" if key == "payment_intent" else None)
        
        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "fingerprint_from_pi"
        mock_stripe_payment_intent.retrieve.assert_called_once_with("pi_123", expand=["payment_method"])

    @patch('app.services.webhook_service.stripe.SetupIntent')
    async def test_get_fingerprint_from_setup_intent(self, mock_stripe_setup_intent: MagicMock, webhook_service: WebhookService):
        mock_si = MagicMock()
        mock_si.payment_method = MagicMock()
        mock_si.payment_method.card = MagicMock()
        mock_si.payment_method.card.fingerprint = "fingerprint_from_si"
        mock_stripe_setup_intent.retrieve.return_value = mock_si

        event_data = MagicMock()
        event_data.get = MagicMock(side_effect=lambda key: "si_123" if key == "setup_intent" else None)

        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "fingerprint_from_si"
        mock_stripe_setup_intent.retrieve.assert_called_once_with("si_123", expand=["payment_method"])

    @patch('app.services.webhook_service.stripe.PaymentMethod')
    async def test_get_fingerprint_from_default_payment_method(self, mock_stripe_payment_method: MagicMock, webhook_service: WebhookService):
        mock_pm = MagicMock()
        mock_pm.card = MagicMock()
        mock_pm.card.fingerprint = "fingerprint_from_dpm"
        mock_stripe_payment_method.retrieve.return_value = mock_pm

        event_data = MagicMock()
        event_data.get = MagicMock(side_effect=lambda key: "pm_123" if key == "default_payment_method" else None)

        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "fingerprint_from_dpm"
        mock_stripe_payment_method.retrieve.assert_called_once_with("pm_123")

    async def test_get_fingerprint_from_event_data_direct(self, webhook_service: WebhookService):
        event_data = MagicMock()
        event_data.get = MagicMock(side_effect=lambda key, default={}: 
            {"card": {"fingerprint": "direct_fingerprint"}} if key == "payment_method_details" else default.get(key) if isinstance(default, dict) else None
        )
        
        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "direct_fingerprint"

    @patch('app.services.webhook_service.stripe.PaymentIntent')
    async def test_get_fingerprint_stripe_error(self, mock_stripe_payment_intent: MagicMock, webhook_service: WebhookService, mock_logger: MagicMock):
        mock_stripe_payment_intent.retrieve.side_effect = stripe.error.StripeError("Stripe API Down")
        
        event_data = MagicMock()
        event_data.get = MagicMock(side_effect=lambda key: "pi_error" if key == "payment_intent" else None)

        with patch('app.services.webhook_service.logger', mock_logger):
            fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_stripe_err")
        
        assert fingerprint is None
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger') # Patch logger for all tests in this class
class TestHandleCheckoutSessionCompleted:
    """Tests for handle_checkout_session_completed."""

    # TODO: Implement tests based on task file
    # - Test unique fingerprint: trial proceeds, fingerprint stored, user.trial.started potentially published.
    # - Test duplicate fingerprint: trial rejected, no credits granted, appropriate logging/event.
    # - Test correct parsing of Stripe checkout.session.completed event payload.
    # - Test no user_id in event.
    # - Test no card_fingerprint found.
    # - Test Stripe API error when cancelling subscription.
    # - Test DB error when updating user status.

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService):
        event_payload = {
            "id": "cs_test_no_user",
            "client_reference_id": None,
            "metadata": {},
            "customer": "cus_test_customer",
            "subscription": "sub_test_subscription"
        }
        event = create_stripe_event_payload(event_type="checkout.session.completed", data_object=event_payload)
        
        await webhook_service.handle_checkout_session_completed(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found in checkout.session.completed event: {event.id}",
            event_id=event.id
        )
        webhook_service.db.execute.assert_not_called() # No DB interaction if no user_id

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_no_card_fingerprint_logs_warning_and_returns(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock
    ):
        mock_get_fingerprint.return_value = None
        event_payload = {
            "id": "cs_test_no_fp",
            "client_reference_id": "user_123",
            "customer": "cus_test_customer",
            "subscription": "sub_test_subscription"
        }
        event = create_stripe_event_payload(event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_logger.warning.assert_called_with(
            f"Card fingerprint not found for checkout.session.completed: {event.id}. Cannot perform trial uniqueness check.",
            event_id=event.id
        )
        # Ensure no further processing like fingerprint check in DB happens
        mock_db_session.execute.assert_not_called() 

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription')
    async def test_duplicate_fingerprint_cancels_stripe_sub_updates_user_publishes_event(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        card_fingerprint = "fp_duplicate_card"
        user_id = "user_123_dup"
        stripe_customer_id = "cus_test_customer_dup"
        stripe_subscription_id = "sub_test_subscription_dup"
        event_id = "evt_checkout_dup_fp"

        mock_get_fingerprint.return_value = card_fingerprint
        
        # Mock DB query for existing fingerprint
        mock_existing_fp_use = MagicMock(spec=UsedTrialCardFingerprint)
        mock_existing_fp_use.user_id = "user_other"
        mock_existing_fp_use.stripe_subscription_id = "sub_other"
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = mock_existing_fp_use
        
        # Mock User object for update
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.account_status = "pending" # Initial status
        mock_db_session.get.return_value = mock_user

        event_payload = {
            "id": "cs_test_dup_fp",
            "client_reference_id": user_id,
            "customer": stripe_customer_id,
            "subscription": stripe_subscription_id,
            "metadata": {"user_id": user_id} # Ensure user_id is available
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        
        # Check fingerprint DB lookup
        assert mock_db_session.execute.call_args_list[0][0][0].text.startswith("SELECT used_trial_card_fingerprints") # Basic check

        # Check Stripe subscription cancellation
        mock_stripe_sub_api.delete.assert_called_once_with(stripe_subscription_id)
        
        # Check user update
        mock_db_session.get.assert_called_once_with(User, user_id)
        assert mock_user.account_status == "trial_rejected"
        mock_db_session.commit.assert_any_call() # Called for user update

        # Check event publishing
        mock_event_publisher.publish_user_trial_blocked.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )
        mock_logger.warning.assert_any_call(
            f"Duplicate card fingerprint detected for trial attempt: User ID {user_id}, Fingerprint {card_fingerprint}",
            event_id=event_id,
            user_id=user_id,
            card_fingerprint=card_fingerprint,
            existing_use_user_id=mock_existing_fp_use.user_id,
            existing_use_subscription_id=mock_existing_fp_use.stripe_subscription_id
        )

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription')
    async def test_duplicate_fingerprint_stripe_api_error_on_cancel(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        card_fingerprint = "fp_dup_stripe_err"
        user_id = "user_stripe_err"
        stripe_customer_id = "cus_stripe_err"
        stripe_subscription_id = "sub_stripe_err"
        event_id = "evt_checkout_stripe_err"

        mock_get_fingerprint.return_value = card_fingerprint
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = MagicMock(spec=UsedTrialCardFingerprint) # Existing fingerprint
        mock_stripe_sub_api.delete.side_effect = stripe.error.StripeError("API unavailable")
        
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "pending"
        mock_db_session.get.return_value = mock_user

        event_payload = {"id": "cs_stripe_err", "client_reference_id": user_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id, "metadata": {"user_id": user_id}}
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_stripe_sub_api.delete.assert_called_once_with(stripe_subscription_id)
        mock_logger.error.assert_any_call(
            f"Stripe API error canceling subscription {stripe_subscription_id} due to duplicate fingerprint: API unavailable",
            event_id=event_id,
            stripe_subscription_id=stripe_subscription_id,
            exc_info=True
        )
        # User status should still be updated and event published
        assert mock_user.account_status == "trial_rejected"
        mock_event_publisher.publish_user_trial_blocked.assert_called_once()

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription')
    async def test_duplicate_fingerprint_db_error_on_user_update(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        card_fingerprint = "fp_dup_db_err"
        user_id = "user_db_err"
        stripe_customer_id = "cus_db_err"
        stripe_subscription_id = "sub_db_err"
        event_id = "evt_checkout_db_err"

        mock_get_fingerprint.return_value = card_fingerprint
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = MagicMock(spec=UsedTrialCardFingerprint)
        
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "pending"
        mock_db_session.get.return_value = mock_user
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed") # Error on user update commit

        event_payload = {"id": "cs_db_err", "client_reference_id": user_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id, "metadata": {"user_id": user_id}}
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_stripe_sub_api.delete.assert_called_once_with(stripe_subscription_id) # Stripe cancel still attempted
        mock_db_session.get.assert_called_once_with(User, user_id)
        assert mock_user.account_status == "trial_rejected" # Status is set before commit
        mock_db_session.commit.assert_called_once() # Attempted commit
        mock_db_session.rollback.assert_called_once() # Rolled back due to error
        mock_logger.error.assert_any_call(
            f"DB error updating user {user_id} status to trial_rejected: DB commit failed",
            user_id=user_id, event_id=event_id, exc_info=True
        )
        # Event should still be published as it happens before the problematic commit
        mock_event_publisher.publish_user_trial_blocked.assert_called_once()


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_unique_fingerprint_logs_info(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        card_fingerprint = "fp_unique_card"
        user_id = "user_123_unique"
        event_id = "evt_checkout_unique_fp"

        mock_get_fingerprint.return_value = card_fingerprint
        
        # Mock DB query for existing fingerprint - none found
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None
        
        event_payload = {
            "id": "cs_test_unique_fp",
            "client_reference_id": user_id,
            "customer": "cus_test_customer_unique",
            "subscription": "sub_test_subscription_unique",
            "metadata": {"user_id": user_id}
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        assert mock_db_session.execute.call_args_list[0][0][0].text.startswith("SELECT used_trial_card_fingerprints")
        
        mock_logger.info.assert_any_call(
            f"Card fingerprint {card_fingerprint} is unique for trial. User ID {user_id}.",
            event_id=event_id,
            user_id=user_id,
            card_fingerprint=card_fingerprint
        )
        # No Stripe cancellation, no user status change to rejected, no trial_blocked event
        mock_event_publisher.publish_user_trial_blocked.assert_not_called()
        # db.commit might be called by mark_event_as_processed if that's part of the flow, but not for user update here.


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleCustomerSubscriptionCreated:
    """Tests for handle_customer_subscription_created."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "sub_test_no_user",
            "customer": "cus_test_no_user_mapping",
            "status": "trialing",
            "items": {"data": [{"price": {"id": "price_trial"}}]},
            "metadata": {} # No user_id in metadata
        }
        event = create_stripe_event_payload(event_type="customer.subscription.created", data_object=event_payload)
        
        # Mock DB query for user_id by stripe_customer_id to return None
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None

        await webhook_service.handle_customer_subscription_created(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for customer.subscription.created: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        # Ensure no further significant DB operations like subscription creation or credit grant
        assert mock_db_session.merge.call_count == 0
        assert mock_db_session.add.call_count == 0

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_no_card_fingerprint_raises_value_error(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock
    ):
        user_id = "user_no_fp_sub"
        stripe_subscription_id = "sub_no_fp"
        event_id = "evt_sub_no_fp"

        mock_get_fingerprint.return_value = None # Simulate no fingerprint found

        event_payload = {
            "id": stripe_subscription_id,
            "customer": "cus_for_user_no_fp_sub",
            "status": "trialing", # Critical for fingerprint check
            "items": {"data": [{"price": {"id": "price_trial"}}]},
            "metadata": {"user_id": user_id},
            "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 7,
            "cancel_at_period_end": False,
            "default_payment_method": "pm_123"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        # Mock get_or_create_subscription
        mock_db_sub = MagicMock(spec=Subscription)
        with patch('app.services.webhook_service.get_or_create_subscription', new_callable=AsyncMock, return_value=mock_db_sub):
            with pytest.raises(ValueError) as excinfo:
                await webhook_service.handle_customer_subscription_created(event)
        
        assert str(excinfo.value) == f"Card fingerprint missing for trial subscription {stripe_subscription_id}"
        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_logger.error.assert_called_with(
            f"Card fingerprint not found for trialing subscription {stripe_subscription_id}. Critical for trial logic.",
            event_id=event_id, stripe_subscription_id=stripe_subscription_id
        )
        mock_db_session.commit.assert_not_called() # Should not commit if error raised before

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription')
    async def test_trialing_sub_duplicate_fingerprint_cancels_updates_publishes(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_dup_fp_sub_create"
        stripe_customer_id = "cus_dup_fp_sub"
        stripe_subscription_id = "sub_dup_fp_create"
        card_fingerprint = "fp_duplicate_on_create"
        event_id = "evt_sub_create_dup_fp"

        mock_get_fingerprint.return_value = card_fingerprint

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "trialing",
            "items": {"data": [{"price": {"id": "price_trial"}}]}, "metadata": {"user_id": user_id},
            "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 7,
            "cancel_at_period_end": False, "default_payment_method": "pm_for_dup_fp"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        # Mock get_or_create_subscription
        mock_db_sub = MagicMock(spec=Subscription)
        mock_db_sub.id = 1
        mock_db_sub.user_id = user_id
        mock_db_sub.stripe_subscription_id = stripe_subscription_id
        
        # Mock User for status update
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.account_status = "pending"
        mock_db_session.get.return_value = mock_user
        
        # Simulate IntegrityError when adding UsedTrialCardFingerprint
        mock_db_session.flush = AsyncMock(side_effect=[None, IntegrityError("uq_violation", params={}, orig=None)]) # First flush for subscription, second for fingerprint

        with patch('app.services.webhook_service.get_or_create_subscription', new_callable=AsyncMock, return_value=mock_db_sub):
            await webhook_service.handle_customer_subscription_created(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        
        # Check DB add for fingerprint (attempted)
        # The actual add call happens before the flush that raises IntegrityError
        assert any(isinstance(call_args[0], UsedTrialCardFingerprint) for call_args, _ in mock_db_session.add.call_args_list)

        mock_db_session.rollback.assert_called_once() # Due to IntegrityError
        
        mock_stripe_sub_api.delete.assert_called_once_with(stripe_subscription_id)
        
        assert mock_user.account_status == "trial_rejected"
        assert mock_db_sub.status == "canceled" # Local subscription status updated
        mock_db_session.merge.assert_any_call(mock_user)
        mock_db_session.merge.assert_any_call(mock_db_sub)

        mock_event_publisher.publish_user_trial_blocked.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )
        mock_db_session.commit.assert_called_once() # Final commit for user/sub updates

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_unique_fingerprint_grants_credits_updates_user_publishes_event(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_trial_grant"
        stripe_customer_id = "cus_trial_grant"
        stripe_subscription_id = "sub_trial_grant"
        card_fingerprint = "fp_unique_for_grant"
        event_id = "evt_sub_create_grant"
        trial_end_ts = int(datetime.now(timezone.utc).timestamp()) + 86400
        trial_end_dt = datetime.fromtimestamp(trial_end_ts, timezone.utc)

        mock_get_fingerprint.return_value = card_fingerprint

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "trialing",
            "items": {"data": [{"price": {"id": "price_trial"}}]}, "metadata": {"user_id": user_id},
            "trial_end": trial_end_ts,
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 7,
            "cancel_at_period_end": False, "default_payment_method": "pm_for_grant"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        mock_db_sub = MagicMock(spec=Subscription); mock_db_sub.id = 2
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.has_consumed_initial_trial = False; mock_user.account_status = "pending"
        mock_user_credit = MagicMock(spec=UserCredit); mock_user_credit.id = 1; mock_user_credit.balance = 0
        
        mock_db_session.get.return_value = mock_user
        # Simulate UserCredit lookup: first call for UserCredit, second for User (get)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = mock_user_credit
        
        # Simulate no IntegrityError on fingerprint storage
        mock_db_session.flush = AsyncMock(side_effect=[None, None, None]) # For sub, fingerprint, user_credit, credit_tx

        with patch('app.services.webhook_service.get_or_create_subscription', new_callable=AsyncMock, return_value=mock_db_sub):
            await webhook_service.handle_customer_subscription_created(event)

        # Fingerprint stored
        added_objects = [call_args[0] for call_args, _ in mock_db_session.add.call_args_list]
        assert any(isinstance(obj, UsedTrialCardFingerprint) and obj.stripe_card_fingerprint == card_fingerprint for obj in added_objects)
        
        # Credits granted
        assert mock_user_credit.balance == 10
        assert any(isinstance(obj, CreditTransaction) and obj.amount == 10 and obj.transaction_type == TransactionType.TRIAL_CREDIT_GRANT for obj in added_objects)

        # User updated
        assert mock_user.has_consumed_initial_trial is True
        assert mock_user.account_status == 'trialing'
        
        mock_event_publisher.publish_user_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_dt.isoformat(),
            credits_granted=10
        )
        mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleCustomerSubscriptionUpdated:
    """Tests for handle_customer_subscription_updated."""
    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "sub_update_no_user", "customer": "cus_update_no_user_mapping", "status": "active",
            "items": {"data": [{"price": {"id": "price_active"}}]}, "metadata": {}
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # No user found by stripe_customer_id

        await webhook_service.handle_customer_subscription_updated(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for customer.subscription.updated: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()

    async def test_local_subscription_not_found_creates_one_and_updates(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_sub_not_found"
        stripe_customer_id = "cus_sub_not_found"
        stripe_subscription_id = "sub_not_found_create"
        event_id = "evt_sub_update_create"

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "active",
            "items": {"data": [{"price": {"id": "price_newly_active"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 30,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.updated", data_object=event_payload)

        # Mock DB query for subscription to return None initially
        mock_subscription_select_result = AsyncMock()
        mock_subscription_select_result.scalars.return_value.first.return_value = None
        mock_db_session.execute.return_value = mock_subscription_select_result
        
        # Mock get_or_create_subscription to return a new subscription object
        mock_new_db_sub = MagicMock(spec=Subscription)
        mock_new_db_sub.stripe_customer_id = None # Simulate it might be missing initially
        
        # Mock User for status update
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "trialing"
        mock_db_session.get.return_value = mock_user

        with patch('app.services.webhook_service.get_or_create_subscription', new_callable=AsyncMock, return_value=mock_new_db_sub) as mock_get_or_create:
            await webhook_service.handle_customer_subscription_updated(event)

        mock_get_or_create.assert_called_once_with(mock_db_session, user_id, stripe_subscription_id)
        assert mock_new_db_sub.stripe_customer_id == stripe_customer_id # Ensure it's set
        assert mock_new_db_sub.status == "active"
        assert mock_user.account_status == "active"
        
        mock_db_session.merge.assert_any_call(mock_new_db_sub)
        mock_db_session.commit.assert_called_once()
        mock_event_publisher.publish_user_account_unfrozen.assert_not_called() # Not frozen -> active

    @pytest.mark.parametrize("initial_user_status, stripe_sub_status, expected_user_status, frozen_event_called, unfrozen_event_called", [
        ("trialing", "active", "active", False, False),
        ("active", "past_due", "frozen", True, False),
        ("active", "incomplete", "frozen", True, False),
        ("active", "unpaid", "frozen", True, False),
        ("frozen", "active", "active", False, True),
        ("active", "canceled", "canceled", False, False),
        ("trialing", "canceled", "canceled", False, False),
        ("frozen", "canceled", "canceled", False, False), # Account was frozen, sub canceled, remains canceled (not unfrozen by this)
    ])
    async def test_subscription_status_transitions_update_user_and_publish_events(
        self, initial_user_status: str, stripe_sub_status: str, expected_user_status: str,
        frozen_event_called: bool, unfrozen_event_called: bool,
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = f"user_{stripe_sub_status}"
        stripe_customer_id = f"cus_{stripe_sub_status}"
        stripe_subscription_id = f"sub_{stripe_sub_status}"
        event_id = f"evt_sub_update_{stripe_sub_status}"

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": stripe_sub_status,
            "items": {"data": [{"price": {"id": f"price_{stripe_sub_status}"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 30,
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.updated", data_object=event_payload)

        mock_db_sub = MagicMock(spec=Subscription); mock_db_sub.status = "some_initial_sub_status"
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = initial_user_status
        
        mock_subscription_select_result = AsyncMock()
        mock_subscription_select_result.scalars.return_value.first.return_value = mock_db_sub
        mock_db_session.execute.return_value = mock_subscription_select_result
        mock_db_session.get.return_value = mock_user

        await webhook_service.handle_customer_subscription_updated(event)

        assert mock_db_sub.status == stripe_sub_status
        assert mock_user.account_status == expected_user_status
        
        if frozen_event_called:
            mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id,
                reason="subscription_status_change"
            )
        else:
            mock_event_publisher.publish_user_account_frozen.assert_not_called()

        if unfrozen_event_called:
            mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id,
                reason="subscription_status_change"
            )
        else:
            mock_event_publisher.publish_user_account_unfrozen.assert_not_called()
            
        mock_db_session.commit.assert_called_once()

    async def test_user_not_found_logs_error_rolls_back(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_not_exist_update"
        stripe_subscription_id = "sub_user_not_exist"
        event_payload = {
            "id": stripe_subscription_id, "customer": "cus_user_not_exist", "status": "active",
            "metadata": {"user_id": user_id}
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_db_sub = MagicMock(spec=Subscription)
        mock_subscription_select_result = AsyncMock()
        mock_subscription_select_result.scalars.return_value.first.return_value = mock_db_sub
        mock_db_session.execute.return_value = mock_subscription_select_result
        mock_db_session.get.return_value = None # User not found

        await webhook_service.handle_customer_subscription_updated(event)

        mock_logger.error.assert_called_with(
            f"User {user_id} not found when updating account status for subscription {stripe_subscription_id}.",
            event_id=event.id, user_id=user_id
        )
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()

    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_commit_err_update"
        event_payload = {
            "id": "sub_commit_err", "customer": "cus_commit_err", "status": "active",
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 30,
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_db_sub = MagicMock(spec=Subscription)
        mock_user = MagicMock(spec=User); mock_user.account_status = "trialing"
        
        mock_subscription_select_result = AsyncMock()
        mock_subscription_select_result.scalars.return_value.first.return_value = mock_db_sub
        mock_db_session.execute.return_value = mock_subscription_select_result
        mock_db_session.get.return_value = mock_user
        mock_db_session.commit.side_effect = SQLAlchemyError("Commit failed")

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_customer_subscription_updated(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"DB commit error for customer.subscription.updated {event.id}: Commit failed",
            event_id=event.id, exc_info=True
        )


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentSucceeded:
    """Tests for handle_invoice_payment_succeeded."""
    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "in_no_user", "customer": "cus_no_user_mapping_invoice", "subscription": "sub_for_invoice",
            "customer_details": {"metadata": {}}, # No user_id
            "amount_paid": 1000, "currency": "usd", "billing_reason": "subscription_cycle", "invoice_pdf": "url_pdf"
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # No user found by stripe_customer_id

        await webhook_service.handle_invoice_payment_succeeded(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for invoice.payment_succeeded: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()

    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_not_exist_invoice"
        event_payload = {
            "id": "in_user_not_found", "customer": "cus_user_not_found_invoice", "subscription": "sub_for_invoice",
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": 1000, "currency": "usd", "billing_reason": "subscription_cycle", "invoice_pdf": "url_pdf"
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
        mock_db_session.get.return_value = None # User not found by ID

        await webhook_service.handle_invoice_payment_succeeded(event)

        mock_logger.error.assert_called_with(
            f"User {user_id} not found for invoice.payment_succeeded: {event.id}",
            event_id=event.id, user_id=user_id
        )
        mock_db_session.commit.assert_not_called()

    @pytest.mark.parametrize("initial_user_status, initial_sub_status, expected_user_status, unfrozen_event_should_fire", [
        ("trialing", "trialing", "active", False),
        ("frozen", "past_due", "active", True),
        ("active", "active", "active", False), # No status change, no unfrozen event
        ("pending", "active", "active", False),
    ])
    async def test_payment_succeeded_updates_statuses_and_publishes_events(
        self, initial_user_status: str, initial_sub_status: str, expected_user_status: str, unfrozen_event_should_fire: bool,
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = f"user_inv_paid_{initial_user_status}"
        stripe_customer_id = f"cus_inv_paid_{initial_user_status}"
        stripe_subscription_id = f"sub_inv_paid_{initial_user_status}"
        stripe_invoice_id = f"in_paid_{initial_user_status}"
        event_id = f"evt_inv_paid_{initial_user_status}"

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id,
            "customer_details": {"metadata": {"user_id": user_id}}, # Assuming user_id is in customer metadata
            "amount_paid": 2000, "currency": "usd",
            "billing_reason": "subscription_cycle", "invoice_pdf": "http://example.com/invoice.pdf"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = initial_user_status
        mock_subscription = MagicMock(spec=Subscription); mock_subscription.status = initial_sub_status
        
        mock_db_session.get.return_value = mock_user
        
        mock_sub_select_result = AsyncMock()
        mock_sub_select_result.scalars.return_value.first.return_value = mock_subscription
        mock_db_session.execute.return_value = mock_sub_select_result # For subscription lookup

        await webhook_service.handle_invoice_payment_succeeded(event)

        assert mock_user.account_status == expected_user_status
        if stripe_subscription_id: # Subscription related invoice
            assert mock_subscription.status == "active" # Should be set to active
            mock_db_session.merge.assert_any_call(mock_subscription)
        
        mock_event_publisher.publish_user_invoice_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            amount_paid=event.data.object.amount_paid,
            currency=event.data.object.currency,
            billing_reason=event.data.object.billing_reason,
            invoice_pdf_url=event.data.object.invoice_pdf
        )

        if unfrozen_event_should_fire:
            mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                reason="invoice_paid_after_failure"
            )
        else:
            mock_event_publisher.publish_user_account_unfrozen.assert_not_called()
            
        mock_db_session.commit.assert_called_once()

    async def test_payment_succeeded_no_subscription_updates_user_publishes_invoice_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_inv_paid_no_sub"
        stripe_customer_id = "cus_inv_paid_no_sub"
        stripe_invoice_id = "in_paid_no_sub"
        event_id = "evt_inv_paid_no_sub"

        event_payload = { # No "subscription" field
            "id": stripe_invoice_id, "customer": stripe_customer_id,
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": 500, "currency": "eur",
            "billing_reason": "manual_charge", "invoice_pdf": "http://example.com/invoice_manual.pdf"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "pending"
        mock_db_session.get.return_value = mock_user
        # No subscription lookup needed as event.data.object.subscription will be None

        await webhook_service.handle_invoice_payment_succeeded(event)

        assert mock_user.account_status == "active" # User becomes active
        
        mock_event_publisher.publish_user_invoice_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=None, # Important: no subscription ID
            stripe_invoice_id=stripe_invoice_id,
            amount_paid=event.data.object.amount_paid,
            currency=event.data.object.currency,
            billing_reason=event.data.object.billing_reason,
            invoice_pdf_url=event.data.object.invoice_pdf
        )
        mock_event_publisher.publish_user_account_unfrozen.assert_not_called() # No prior frozen state assumed for non-sub invoice
        mock_db_session.commit.assert_called_once()


    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_commit_err_inv_paid"
        event_payload = {
            "id": "in_commit_err", "customer": "cus_commit_err_inv", "subscription": "sub_commit_err_inv",
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": 100, "currency": "gbp"
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user = MagicMock(spec=User); mock_user.account_status = "frozen"
        mock_subscription = MagicMock(spec=Subscription); mock_subscription.status = "past_due"
        
        mock_db_session.get.return_value = mock_user
        mock_sub_select_result = AsyncMock()
        mock_sub_select_result.scalars.return_value.first.return_value = mock_subscription
        mock_db_session.execute.return_value = mock_sub_select_result
        
        mock_db_session.commit.side_effect = SQLAlchemyError("Commit failed")

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_invoice_payment_succeeded(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"DB commit error for invoice.payment_succeeded {event.id}: Commit failed",
            event_id=event.id, exc_info=True
        )


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentFailed:
    """Tests for handle_invoice_payment_failed."""
    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "in_fail_no_user", "customer": "cus_fail_no_user_mapping", "subscription": "sub_for_fail_invoice",
            "customer_details": {"metadata": {}},
            "last_payment_error": {"message": "Card declined"}, "next_payment_attempt": None, "charge": "ch_fail"
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None

        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for invoice.payment_failed: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()

    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_not_exist_inv_fail"
        event_payload = {
            "id": "in_fail_user_not_found", "customer": "cus_user_not_found_inv_fail", "subscription": "sub_for_fail_invoice",
            "customer_details": {"metadata": {"user_id": user_id}},
            "last_payment_error": {"message": "Card declined"}
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.get.return_value = None

        await webhook_service.handle_invoice_payment_failed(event)

        mock_logger.error.assert_called_with(
            f"User {user_id} not found for invoice.payment_failed: {event.id}",
            event_id=event.id, user_id=user_id
        )
        mock_db_session.commit.assert_not_called()

    @pytest.mark.parametrize("initial_user_status, billing_reason, expected_user_status, frozen_event_should_fire, needs_commit_expected", [
        ("active", "subscription_cycle", "frozen", True, True),
        ("trialing", "subscription_create", "frozen", True, True),
        ("frozen", "subscription_update", "frozen", False, False), # Already frozen, no new event, no commit for user status
        ("active", "manual_charge", "active", False, False), # Not a subscription billing reason, no status change
    ])
    async def test_payment_failed_updates_status_publishes_events_conditionally(
        self, initial_user_status: str, billing_reason: str, expected_user_status: str,
        frozen_event_should_fire: bool, needs_commit_expected: bool,
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = f"user_inv_fail_{initial_user_status}_{billing_reason.replace('_', '')}"
        stripe_customer_id = f"cus_inv_fail_{initial_user_status}"
        stripe_subscription_id = f"sub_inv_fail_{initial_user_status}" if "subscription" in billing_reason else None
        stripe_invoice_id = f"in_fail_{initial_user_status}"
        event_id = f"evt_inv_fail_{initial_user_status}"
        next_payment_ts = int(datetime.now(timezone.utc).timestamp()) + 86400 * 3
        next_payment_iso = datetime.fromtimestamp(next_payment_ts, timezone.utc).isoformat()


        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id,
            "customer_details": {"metadata": {"user_id": user_id}},
            "billing_reason": billing_reason,
            "last_payment_error": {"message": "Insufficient funds"},
            "charge": "ch_failed_charge",
            "next_payment_attempt": next_payment_ts
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_failed", data_object=event_payload)

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = initial_user_status
        mock_subscription = MagicMock(spec=Subscription) if stripe_subscription_id else None
        
        mock_db_session.get.return_value = mock_user
        if stripe_subscription_id:
            mock_sub_select_result = AsyncMock()
            mock_sub_select_result.scalars.return_value.first.return_value = mock_subscription
            mock_db_session.execute.return_value = mock_sub_select_result
        else: # Ensure execute is not problematic if no subscription
            mock_db_session.execute.return_value.scalars.return_value.first.return_value = None


        await webhook_service.handle_invoice_payment_failed(event)

        assert mock_user.account_status == expected_user_status
        
        mock_event_publisher.publish_user_invoice_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_charge_id=event.data.object.charge,
            failure_reason=event.data.object.last_payment_error.message,
            next_payment_attempt_date=next_payment_iso
        )

        if frozen_event_should_fire:
            mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                reason="invoice_payment_failed"
            )
        else:
            mock_event_publisher.publish_user_account_frozen.assert_not_called()
            
        if needs_commit_expected:
            mock_db_session.commit.assert_called_once()
        else:
            mock_db_session.commit.assert_not_called() # Only called if user status actually changed

    async def test_db_commit_error_if_needed_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_commit_err_inv_fail"
        event_payload = {
            "id": "in_commit_err_fail", "customer": "cus_commit_err_inv_fail", "subscription": "sub_commit_err_inv_fail",
            "customer_details": {"metadata": {"user_id": user_id}},
            "billing_reason": "subscription_cycle", # This will trigger needs_commit
            "last_payment_error": {"message": "Expired card"}
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)

        mock_user = MagicMock(spec=User); mock_user.account_status = "active" # To ensure status changes
        mock_subscription = MagicMock(spec=Subscription)
        
        mock_db_session.get.return_value = mock_user
        mock_sub_select_result = AsyncMock()
        mock_sub_select_result.scalars.return_value.first.return_value = mock_subscription
        mock_db_session.execute.return_value = mock_sub_select_result
        
        mock_db_session.commit.side_effect = SQLAlchemyError("Commit failed during fail")

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_invoice_payment_failed(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"DB commit error for invoice.payment_failed {event.id}: Commit failed during fail",
            event_id=event.id, exc_info=True
        )