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
        
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.stripe_customer_id = event.data.object.customer
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = mock_user # User found by stripe_customer_id

        with pytest.raises(ValueError) as excinfo:
            await webhook_service.handle_customer_subscription_created(event)

        assert "Card fingerprint is required for trial subscriptions but not found" in str(excinfo.value)
        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_logger.error.assert_called_once() # Check that an error was logged
        # Ensure no subscription is created or credits granted
        mock_db_session.merge.assert_not_called() 
        mock_db_session.add.assert_not_called()

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription')
    async def test_trialing_sub_duplicate_fingerprint_cancels_updates_publishes(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_dup_fp_sub_create"
        stripe_subscription_id = "sub_dup_fp_create"
        stripe_customer_id = "cus_dup_fp_sub_create"
        card_fingerprint = "fp_duplicate_on_create"
        event_id = "evt_sub_create_dup_fp"

        mock_get_fingerprint.return_value = card_fingerprint

        # Mock user lookup by stripe_customer_id
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.stripe_customer_id = stripe_customer_id
        mock_user.account_status = "pending_trial" # Initial status
        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            mock_user, # First call for user lookup by stripe_customer_id
            MagicMock(spec=UsedTrialCardFingerprint) # Second call for existing fingerprint lookup
        ]
        
        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "trialing",
            "items": {"data": [{"price": {"id": "price_trial"}}]}, "metadata": {"user_id": user_id}, # user_id in metadata for direct use
            "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400,
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400 * 7,
            "cancel_at_period_end": False, "default_payment_method": "pm_123"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        await webhook_service.handle_customer_subscription_created(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        
        # Check Stripe subscription cancellation
        mock_stripe_sub_api.delete.assert_called_once_with(stripe_subscription_id)
        
        # Check user update (status to trial_rejected)
        assert mock_user.account_status == "trial_rejected"
        mock_db_session.commit.assert_any_call() # For user update

        # Check event publishing
        mock_event_publisher.publish_user_trial_blocked.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="duplicate_card_fingerprint",
            blocked_card_fingerprint=card_fingerprint
        )
        mock_logger.warning.assert_any_call(
            f"Duplicate card fingerprint {card_fingerprint} detected for new trial subscription {stripe_subscription_id}. User ID {user_id}.",
            event_id=event_id, user_id=user_id, card_fingerprint=card_fingerprint
        )
        # Ensure no subscription record is created in DB
        mock_db_session.merge.assert_not_called() # Or check specific calls if merge is used elsewhere

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_unique_fingerprint_grants_credits_updates_user_publishes_event(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_unique_fp_sub_create"
        stripe_subscription_id = "sub_unique_fp_create"
        stripe_customer_id = "cus_unique_fp_sub_create"
        card_fingerprint = "fp_unique_on_create"
        event_id = "evt_sub_create_unique_fp"
        trial_end_ts = int(datetime.now(timezone.utc).timestamp()) + 86400 * 7
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = trial_end_ts # For trials, often aligned

        mock_get_fingerprint.return_value = card_fingerprint

        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.stripe_customer_id = stripe_customer_id
        mock_user.account_status = "pending_trial"
        mock_user.has_consumed_initial_trial = False # IMPORTANT: User has not consumed trial credits

        # Simulate user found by stripe_customer_id, then no existing fingerprint
        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            mock_user, # User lookup
            None       # Fingerprint lookup (unique)
        ]
        
        # Mock UserCredit object for the .merge() call to return
        mock_user_credit = UserCredit(user_id=user_id, balance=0) # Initial balance before trial credits
        mock_db_session.merge.return_value = mock_user_credit # For UserCredit merge

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "trialing",
            "items": {"data": [{"price": {"id": settings.STRIPE_FREE_TRIAL_PRICE_ID}}]}, # Use configured trial price ID
            "metadata": {"user_id": user_id},
            "trial_end": trial_end_ts,
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False, "default_payment_method": "pm_123"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        with patch('app.services.webhook_service.settings', STRIPE_FREE_TRIAL_PRICE_ID="price_trial_configured", FREE_TRIAL_CREDITS_AMOUNT=10):
            await webhook_service.handle_customer_subscription_created(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        
        # Check Subscription creation/update (merge)
        # First merge is for Subscription, second for UserCredit
        assert mock_db_session.merge.call_count >= 1 # At least one for Subscription
        merged_subscription_arg = next(c.args[0] for c in mock_db_session.merge.call_args_list if isinstance(c.args[0], Subscription))
        assert merged_subscription_arg.stripe_subscription_id == stripe_subscription_id
        assert merged_subscription_arg.user_id == user_id
        assert merged_subscription_arg.status == "trialing"
        
        # Check UserCredit update
        assert mock_user_credit.balance == settings.FREE_TRIAL_CREDITS_AMOUNT

        # Check User status update
        assert mock_user.account_status == "trialing"
        assert mock_user.has_consumed_initial_trial is True

        # Check UsedTrialCardFingerprint creation
        # This is an `add` call
        added_fingerprint_arg = next(c.args[0] for c in mock_db_session.add.call_args_list if isinstance(c.args[0], UsedTrialCardFingerprint))
        assert added_fingerprint_arg.stripe_card_fingerprint == card_fingerprint
        assert added_fingerprint_arg.user_id == user_id
        
        mock_db_session.commit.assert_any_call()

        # Check event publishing
        mock_event_publisher.publish_user_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=datetime.fromtimestamp(trial_end_ts, tz=timezone.utc),
            credits_granted=settings.FREE_TRIAL_CREDITS_AMOUNT
        )
        mock_logger.info.assert_any_call(
            f"Trial subscription {stripe_subscription_id} created for user {user_id}. Fingerprint {card_fingerprint} recorded.",
            event_id=event_id
        )

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_user_already_consumed_trial(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock,
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_consumed_trial"
        stripe_subscription_id = "sub_consumed_trial"
        card_fingerprint = "fp_consumed_trial" # Assume unique fingerprint for this new attempt
        event_id = "evt_sub_create_consumed"

        mock_get_fingerprint.return_value = card_fingerprint

        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.has_consumed_initial_trial = True # IMPORTANT: User has already consumed trial credits

        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            mock_user, # User lookup
            None       # Fingerprint lookup (unique for this attempt)
        ]
        
        event_payload = {
            "id": stripe_subscription_id, "status": "trialing", "customer": "cus_consumed",
            "items": {"data": [{"price": {"id": settings.STRIPE_FREE_TRIAL_PRICE_ID}}]},
            "metadata": {"user_id": user_id}, "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        with patch('app.services.webhook_service.settings', STRIPE_FREE_TRIAL_PRICE_ID="price_trial_configured", FREE_TRIAL_CREDITS_AMOUNT=10):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_logger.warning.assert_any_call(
            f"User {user_id} attempting new trial subscription {stripe_subscription_id}, but 'has_consumed_initial_trial' is true. No trial credits granted.",
            event_id=event_id
        )
        # Subscription and fingerprint should still be recorded, user status updated
        assert mock_db_session.merge.call_count >= 1 # For Subscription
        assert mock_db_session.add.call_count >= 1 # For UsedTrialCardFingerprint
        assert mock_user.account_status == "trialing" # User is trialing the plan
        
        # CRITICAL: No trial_started event, no credits granted
        mock_event_publisher.publish_user_trial_started.assert_not_called()
        # Check that UserCredit balance was not changed (or not merged/added if it didn't exist)
        # This requires knowing if UserCredit merge/add happens regardless of credit grant.
        # Assuming UserCredit merge happens, its balance should remain unchanged if it existed, or be 0 if new.
        # For simplicity, let's assume if FREE_TRIAL_CREDITS_AMOUNT is 0, it won't add.
        # The current code adds credits if amount > 0. If user consumed, amount is effectively 0 for this path.
        # So, UserCredit.balance should not increase.

    async def test_db_error_during_subscription_update_create_rolls_back_and_raises(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock
    ):
        user_id = "user_db_error_sub_create"
        event_id = "evt_sub_create_db_err"
        
        # Simulate get_card_fingerprint returning a valid fingerprint
        mock_get_fingerprint_patch = patch.object(webhook_service, 'get_card_fingerprint_from_event', AsyncMock(return_value="fp_db_error"))
        
        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.has_consumed_initial_trial = False
        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            mock_user, # User lookup
            None       # Fingerprint lookup (unique)
        ]
        # Make one of the DB operations fail
        mock_db_session.merge.side_effect = SQLAlchemyError("DB merge boom!")

        event_payload = {
            "id": "sub_db_error", "status": "trialing", "customer": "cus_db_error",
            "items": {"data": [{"price": {"id": "price_trial"}}]}, "metadata": {"user_id": user_id},
            "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        with mock_get_fingerprint_patch, pytest.raises(SQLAlchemyError):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"Database error processing customer.subscription.created for event {event.id}: DB merge boom!",
            event_id=event.id, exc_info=True
        )

    async def test_final_db_commit_error_rolls_back_and_raises(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_final_commit_err"
        event_id = "evt_sub_create_final_commit_err"
        card_fingerprint = "fp_final_commit"
        
        mock_get_fingerprint_patch = patch.object(webhook_service, 'get_card_fingerprint_from_event', AsyncMock(return_value=card_fingerprint))
        
        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.has_consumed_initial_trial = False
        mock_user.account_status = "pending_trial"

        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [mock_user, None]
        
        # Mock UserCredit merge to succeed
        mock_user_credit = UserCredit(user_id=user_id, balance=0)
        mock_db_session.merge.side_effect = lambda instance: mock_user_credit if isinstance(instance, UserCredit) else MagicMock()

        # Make the final commit fail
        mock_db_session.commit.side_effect = SQLAlchemyError("Final commit boom!")

        event_payload = {
            "id": "sub_final_commit", "status": "trialing", "customer": "cus_final_commit",
            "items": {"data": [{"price": {"id": settings.STRIPE_FREE_TRIAL_PRICE_ID}}]},
            "metadata": {"user_id": user_id}, "trial_end": int(datetime.now(timezone.utc).timestamp()) + 86400
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        with mock_get_fingerprint_patch, \
             patch('app.services.webhook_service.settings', STRIPE_FREE_TRIAL_PRICE_ID="price_trial_cfg", FREE_TRIAL_CREDITS_AMOUNT=10), \
             pytest.raises(SQLAlchemyError):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"Database error processing customer.subscription.created for event {event.id}: Final commit boom!",
            event_id=event.id, exc_info=True
        )
        # Event publisher should not have been called if commit failed
        mock_event_publisher.publish_user_trial_started.assert_not_called()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleCustomerSubscriptionUpdated:
    """Tests for handle_customer_subscription_updated."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "sub_update_no_user", "customer": "cus_no_user_for_update", "status": "active",
            "items": {"data": [{"price": {"id": "price_active"}}]}, "metadata": {}
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # User not found by customer_id

        await webhook_service.handle_customer_subscription_updated(event)
        mock_logger.error.assert_called_with(
            f"User ID not found for customer.subscription.updated: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.merge.assert_not_called()

    async def test_local_subscription_not_found_creates_one_and_updates(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_sub_updated_new_local"
        stripe_subscription_id = "sub_updated_new_local"
        stripe_customer_id = "cus_sub_updated_new_local"
        event_id = "evt_sub_updated_new_local"
        current_period_end_ts = int(datetime.now(timezone.utc).timestamp()) + 86400 * 15

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.stripe_customer_id = stripe_customer_id
        mock_user.account_status = "active" # Assume user is active

        # User found, but no existing subscription for this stripe_subscription_id
        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            mock_user, # User lookup by customer_id
            None       # Subscription lookup by stripe_subscription_id
        ]
        
        # Mock the merge call to return the instance passed to it
        mock_db_session.merge.side_effect = lambda instance: instance

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": "active",
            "items": {"data": [{"price": {"id": "price_some_plan"}}]}, "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.updated", data_object=event_payload)

        await webhook_service.handle_customer_subscription_updated(event)

        # Check that a new subscription was merged
        merged_subscription_arg = next(c.args[0] for c in mock_db_session.merge.call_args_list if isinstance(c.args[0], Subscription))
        assert merged_subscription_arg.stripe_subscription_id == stripe_subscription_id
        assert merged_subscription_arg.user_id == user_id
        assert merged_subscription_arg.status == "active"
        
        mock_db_session.commit.assert_any_call()
        mock_logger.info.assert_any_call(
            f"Customer subscription {stripe_subscription_id} for user {user_id} updated (new local record created). Status: active",
            event_id=event_id
        )
        # No account status change events expected if user was already active and sub became active
        mock_event_publisher.publish_user_account_frozen.assert_not_called()
        mock_event_publisher.publish_user_account_unfrozen.assert_not_called()

    #    @pytest.mark.parametrize("initial_user_status, stripe_sub_status, expected_user_status, frozen_event_called, unfrozen_event_called", [
        #        ("trialing", "active", "active", False, False),
        #        ("active", "past_due", "frozen", True, False),
        #        ("active", "incomplete", "frozen", True, False),
        #        ("active", "unpaid", "frozen", True, False),
        #        ("frozen", "active", "active", False, True),
        #        ("active", "canceled", "canceled", False, False),
        #        ("trialing", "canceled", "canceled", False, False),
        #        ("frozen", "canceled", "canceled", False, False), # Account was frozen, sub canceled, remains canceled (not unfrozen by this)
    #    ])
    #    async def test_subscription_status_transitions_update_user_and_publish_events(
        #        self, initial_user_status: str, stripe_sub_status: str, expected_user_status: str,
        #        frozen_event_called: bool, unfrozen_event_called: bool,
        #        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    #    ):
        #        user_id = f"user_{stripe_sub_status}"
        #        stripe_customer_id = f"cus_{stripe_sub_status}"
        #        stripe_subscription_id = f"sub_{stripe_sub_status}"
        #        event_id = f"evt_sub_updated_{stripe_sub_status}"
        #        current_period_end_ts = int(datetime.now(timezone.utc).timestamp()) + 86400 * 10

        #        mock_user = MagicMock(spec=User)
        #        mock_user.id = user_id
        #        mock_user.stripe_customer_id = stripe_customer_id
        #        mock_user.account_status = initial_user_status # Set initial user account status

        #        mock_local_sub = Subscription(
            #            user_id=user_id, stripe_subscription_id=stripe_subscription_id, 
            #            status="trialing" if initial_user_status == "trialing" else "active", # Some plausible initial local sub status
            #            is_active=True
        #        )

        #        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [
            #            mock_user,       # User lookup
            #            mock_local_sub   # Subscription lookup
        #        ]
        #        mock_db_session.merge.return_value = mock_local_sub # Ensure merge returns the sub

        #        event_payload = {
            #            "id": stripe_subscription_id, "customer": stripe_customer_id, "status": stripe_sub_status,
            #            "items": {"data": [{"price": {"id": "price_plan"}}]}, "metadata": {"user_id": user_id},
            #            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            #            "current_period_end": current_period_end_ts,
            #            "cancel_at_period_end": stripe_sub_status == "canceled"
        #        }
        #        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.updated", data_object=event_payload)

        #        await webhook_service.handle_customer_subscription_updated(event)

        #        assert mock_local_sub.status == stripe_sub_status
        #        assert mock_user.account_status == expected_user_status
        
        #        if frozen_event_called:
            #            mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
                #                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id, reason=f"subscription_{stripe_sub_status}"
            #            )
        #        else:
            #            mock_event_publisher.publish_user_account_frozen.assert_not_called()

        #        if unfrozen_event_called:
            #            mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
                #                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id, reason="subscription_active"
            #            )
        #        else:
            #            mock_event_publisher.publish_user_account_unfrozen.assert_not_called()
        
        #        mock_db_session.commit.assert_any_call()

    async def test_user_not_found_logs_error_rolls_back(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {"id": "sub_user_not_found", "customer": "cus_ghost", "status": "active"}
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)
        
        # Simulate user not found by stripe_customer_id
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None

        await webhook_service.handle_customer_subscription_updated(event)

        mock_logger.error.assert_called_with(
            f"User not found for customer.subscription.updated: {event.id}, Stripe Customer: cus_ghost",
            event_id=event.id, stripe_customer_id="cus_ghost"
        )
        mock_db_session.rollback.assert_not_called() # No transaction to rollback if user not found early
        mock_db_session.commit.assert_not_called()


    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_db_commit_err_sub_update"
        stripe_subscription_id = "sub_db_commit_err"
        event_id = "evt_sub_update_db_commit_err"

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "active"
        mock_local_sub = Subscription(user_id=user_id, stripe_subscription_id=stripe_subscription_id, status="active", is_active=True)

        mock_db_session.execute.return_value.scalars.return_value.first.side_effect = [mock_user, mock_local_sub]
        mock_db_session.merge.return_value = mock_local_sub
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed during sub update")

        event_payload = {
            "id": stripe_subscription_id, "customer": "cus_db_commit_err", "status": "past_due", # e.g. status change
            "items": {"data": [{"price": {"id": "price_plan"}}]}, "metadata": {"user_id": user_id},
            "current_period_end": int(datetime.now(timezone.utc).timestamp()) + 86400
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.updated", data_object=event_payload)

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_customer_subscription_updated(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"Database error processing customer.subscription.updated for event {event.id}: DB commit failed during sub update",
            event_id=event.id, exc_info=True
        )


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentSucceeded:
    """Tests for handle_invoice_payment_succeeded."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "in_no_user", "customer": "cus_inv_no_user", "subscription": "sub_inv_no_user",
            "paid": True, "billing_reason": "subscription_cycle", "lines": {"data": [{"price": {"id": "price_plan"}}]}
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # User not found

        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_logger.error.assert_called_with(
            f"User ID not found for invoice.payment_succeeded: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()

    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        # This case is essentially the same as above if user_id comes from metadata but user is not in DB
        user_id_from_meta = "ghost_user_id"
        event_payload = {
            "id": "in_user_not_found", "customer": "cus_for_ghost", "subscription": "sub_for_ghost",
            "paid": True, "billing_reason": "subscription_cycle", "metadata": {"user_id": user_id_from_meta},
            "lines": {"data": [{"price": {"id": "price_plan"}}]}
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
        
        # Simulate user not found by ID from metadata
        mock_db_session.get.return_value = None 

        await webhook_service.handle_invoice_payment_succeeded(event)
        mock_logger.error.assert_called_with(
            f"User {user_id_from_meta} not found for invoice.payment_succeeded: {event.id}",
            event_id=event.id, user_id=user_id_from_meta
        )
        mock_db_session.commit.assert_not_called()

    #    @pytest.mark.parametrize("initial_user_status, initial_sub_status, expected_user_status, unfrozen_event_should_fire", [ # re-typed
        #        ("trialing", "trialing", "active", False),
        #        ("frozen", "past_due", "active", True),
        #        ("active", "active", "active", False), # No status change, no unfrozen event
        #        ("pending", "active", "active", False),
    #    ])
    #    async def test_payment_succeeded_updates_statuses_and_publishes_events( # re-typed
        #        self, initial_user_status: str, initial_sub_status: str, expected_user_status: str, unfrozen_event_should_fire: bool,
        #        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    #    ):
        #        user_id = f"user_inv_paid_{initial_user_status}"
        #        stripe_customer_id = f"cus_inv_paid_{initial_user_status}"
        #        stripe_subscription_id = f"sub_inv_paid_{initial_user_status}"
        #        stripe_invoice_id = f"in_paid_{initial_user_status}"
        #        event_id = f"evt_inv_paid_{initial_user_status}"

        #        mock_user = MagicMock(spec=User)
        #        mock_user.id = user_id
        #        mock_user.stripe_customer_id = stripe_customer_id
        #        mock_user.account_status = initial_user_status

        #        mock_subscription = None
        #        if stripe_subscription_id:
            #            mock_subscription = Subscription(user_id=user_id, stripe_subscription_id=stripe_subscription_id, status=initial_sub_status, is_active=initial_sub_status in ["active", "trialing"])
        
        ##        # get(User, user_id) then execute().scalars().first() for subscription
        #        mock_db_session.get.return_value = mock_user
        #        mock_db_session.execute.return_value.scalars.return_value.first.return_value = mock_subscription
        #        mock_db_session.merge.return_value = mock_subscription # If subscription is merged

        #        event_payload = {
            #            "id": stripe_invoice_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id,
            #            "paid": True, "billing_reason": "subscription_cycle", "metadata": {"user_id": user_id},
            #            "lines": {"data": [{"price": {"id": "price_some_plan"}, "quantity": 1, "amount": 1000 }]}, # Added amount
            #            "total": 1000, "currency": "usd" # Added total and currency
        #        }
        #        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_succeeded", data_object=event_payload)

        #        await webhook_service.handle_invoice_payment_succeeded(event)

        #        assert mock_user.account_status == expected_user_status
        #        if mock_subscription:
            #            assert mock_subscription.status == "active" # Payment succeeded, sub should be active
            #            assert mock_subscription.is_active is True

        #        if unfrozen_event_should_fire:
            #            mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
                #                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id, reason="invoice_paid"
            #            )
        #        else:
            #            mock_event_publisher.publish_user_account_unfrozen.assert_not_called()

        #        mock_event_publisher.publish_user_invoice_paid.assert_called_once() # Always called on success
        #        mock_db_session.commit.assert_any_call()

    async def test_payment_succeeded_no_subscription_updates_user_publishes_invoice_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_inv_paid_no_sub"
        stripe_customer_id = "cus_inv_paid_no_sub"
        stripe_invoice_id = "in_paid_no_sub"
        event_id = "evt_inv_paid_no_sub"

        mock_user = MagicMock(spec=User)
        mock_user.id = user_id
        mock_user.stripe_customer_id = stripe_customer_id
        mock_user.account_status = "frozen" # e.g., user was frozen for some reason

        mock_db_session.get.return_value = mock_user
        # No subscription found by stripe_subscription_id (which is None in event)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None 

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, "subscription": None, # NO subscription
            "paid": True, "billing_reason": "manual_charge", "metadata": {"user_id": user_id},
            "lines": {"data": [{"price": {"id": "price_one_time"}, "quantity": 1, "amount": 500}]},
            "total": 500, "currency": "usd"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_succeeded", data_object=event_payload)

        await webhook_service.handle_invoice_payment_succeeded(event)

        # User status should become active if it was frozen and a payment succeeded
        assert mock_user.account_status == "active" 
        
        mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
            user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=None, reason="invoice_paid"
        )
        mock_event_publisher.publish_user_invoice_paid.assert_called_once()
        mock_db_session.commit.assert_any_call()


    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_db_err_inv_paid"
        event_id = "evt_inv_paid_db_err"

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "frozen"
        mock_db_session.get.return_value = mock_user
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # No subscription
        
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed inv_paid")

        event_payload = {
            "id": "in_db_err", "customer": "cus_db_err", "subscription": None, "paid": True,
            "billing_reason": "manual_charge", "metadata": {"user_id": user_id},
            "lines": {"data": [{"price": {"id": "price_err"}, "quantity": 1, "amount": 100}]},
            "total": 100, "currency": "usd"
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_succeeded", data_object=event_payload)

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_invoice_payment_succeeded(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"Database error processing invoice.payment_succeeded for event {event.id}: DB commit failed inv_paid",
            event_id=event.id, exc_info=True
        )


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentFailed:
    """Tests for handle_invoice_payment_failed."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "in_fail_no_user", "customer": "cus_inv_fail_no_user", "subscription": "sub_inv_fail_no_user",
            "paid": False, "billing_reason": "subscription_cycle"
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # User not found

        await webhook_service.handle_invoice_payment_failed(event)
        mock_logger.error.assert_called_with(
            f"User ID not found for invoice.payment_failed: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()

    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id_from_meta = "ghost_user_id_fail"
        event_payload = {
            "id": "in_fail_user_not_found", "customer": "cus_for_ghost_fail", "subscription": "sub_for_ghost_fail",
            "paid": False, "billing_reason": "subscription_cycle", "metadata": {"user_id": user_id_from_meta}
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.get.return_value = None # User not found by ID

        await webhook_service.handle_invoice_payment_failed(event)
        mock_logger.error.assert_called_with(
            f"User {user_id_from_meta} not found for invoice.payment_failed: {event.id}",
            event_id=event.id, user_id=user_id_from_meta
        )
        mock_db_session.commit.assert_not_called()

    #    @pytest.mark.parametrize("initial_user_status, billing_reason, expected_user_status, frozen_event_should_fire, needs_commit_expected", [ # re-typed
        #        ("active", "subscription_cycle", "frozen", True, True),
        #        ("trialing", "subscription_create", "frozen", True, True),
        #        ("frozen", "subscription_update", "frozen", False, False), # Already frozen, no new event, no commit for user status
        #        ("active", "manual_charge", "active", False, False), # Not a subscription billing reason, no status change
    #    ])
    #    async def test_payment_failed_updates_status_publishes_events_conditionally( # re-typed
        #        self, initial_user_status: str, billing_reason: str, expected_user_status: str,
        #        frozen_event_should_fire: bool, needs_commit_expected: bool,
        #        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock
    #    ):
        #        user_id = f"user_inv_fail_{initial_user_status}_{billing_reason.replace('_', '')}"
        #        stripe_customer_id = f"cus_inv_fail_{initial_user_status}"
        #        stripe_subscription_id = f"sub_inv_fail_{initial_user_status}" if "subscription" in billing_reason else None
        #        stripe_invoice_id = f"in_fail_{initial_user_status}"
        #        event_id = f"evt_inv_fail_{initial_user_status}"
        #        next_payment_ts = int(datetime.now(timezone.utc).timestamp()) + 86400 * 3

        #        mock_user = MagicMock(spec=User)
        #        mock_user.id = user_id
        #        mock_user.stripe_customer_id = stripe_customer_id
        #        mock_user.account_status = initial_user_status
        
        #        mock_subscription = None
        #        if stripe_subscription_id:
            ##            # If billing_reason is subscription related, we might expect a subscription object
            #            mock_subscription = Subscription(user_id=user_id, stripe_subscription_id=stripe_subscription_id, status="active", is_active=True)

        #        mock_db_session.get.return_value = mock_user
        #        mock_db_session.execute.return_value.scalars.return_value.first.return_value = mock_subscription

        #        event_payload = {
            #            "id": stripe_invoice_id, "customer": stripe_customer_id, "subscription": stripe_subscription_id,
            #            "paid": False, "billing_reason": billing_reason, "metadata": {"user_id": user_id},
            #            "next_payment_attempt": next_payment_ts if billing_reason != "manual_charge" else None,
            #            #            "lines": {"data": [{"price": {"id": "price_plan"}}]}
        #        }
        #        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_failed", data_object=event_payload)

        #        await webhook_service.handle_invoice_payment_failed(event)

        #        assert mock_user.account_status == expected_user_status
        
        #        if frozen_event_should_fire:
            #            mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
                #                user_id=user_id, stripe_customer_id=stripe_customer_id, stripe_subscription_id=stripe_subscription_id, reason=f"invoice_payment_failed_{billing_reason}"
            #            )
        #        else:
            #            mock_event_publisher.publish_user_account_frozen.assert_not_called()

        #        mock_event_publisher.publish_user_invoice_failed.assert_called_once() # Always called on failure

        #        if needs_commit_expected:
            #            mock_db_session.commit.assert_any_call()
        #        else:
            ##            # If no status change was expected, no commit for user status update.
            ##            # Commit might still be called by mark_event_as_processed.
            ##            # This assertion is tricky. Let's focus on whether user status changed.
            ##            # If initial_user_status == expected_user_status, then user.account_status was not set again.
            ##            # The service code: `if user.account_status != new_status: user.account_status = new_status; await db.commit()`
            #            pass # Covered by frozen_event_should_fire and expected_user_status checks

    async def test_db_commit_error_if_needed_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "user_db_err_inv_fail"
        event_id = "evt_inv_fail_db_err"

        mock_user = MagicMock(spec=User); mock_user.id = user_id; mock_user.account_status = "active"
        mock_db_session.get.return_value = mock_user
        mock_db_session.execute.return_value.scalars.return_value.first.return_value = None # No subscription

        # This commit is conditional on user.account_status changing.
        # To force a commit attempt, ensure initial status is different from 'frozen'.
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed inv_fail")

        event_payload = {
            "id": "in_db_err_fail", "customer": "cus_db_err_fail", "subscription": "sub_db_err_fail", # Needs sub for status change logic
            "paid": False, "billing_reason": "subscription_cycle", "metadata": {"user_id": user_id},
            "lines": {"data": [{"price": {"id": "price_err"}}]}
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="invoice.payment_failed", data_object=event_payload)

        with pytest.raises(SQLAlchemyError):
            await webhook_service.handle_invoice_payment_failed(event)
        
        # Rollback should be called if commit was attempted and failed
        mock_db_session.rollback.assert_called_once()
        mock_logger.error.assert_any_call(
            f"Database error processing invoice.payment_failed for event {event.id}: DB commit failed inv_fail",
            event_id=event.id, exc_info=True
        )