import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta # Ensure timedelta is imported

import stripe # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql.expression import Select # Added for type checking
from sqlalchemy.engine import Result, ScalarResult # For spec in mocks
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.services.webhook_service import WebhookService
from app.models.user import User
from app.models.plan import UsedTrialCardFingerprint, Subscription
from app.models.processed_event import ProcessedStripeEvent
from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.services.internal_event_publisher import InternalEventPublisher
from app.core.config import settings 
from app.core.db_utils import get_or_create_subscription


# --- Fixtures ---

@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provides a mock SQLAlchemy AsyncSession."""
    session = AsyncMock(spec=AsyncSession)
    
    # Object returned by (await session.execute(...))
    execute_result_sync_mock = MagicMock(spec=Result) # Result object is sync
    
    # Object returned by execute_result_sync_mock.scalars()
    # This object has an async .first() method
    scalars_provider_async_mock = AsyncMock(spec=ScalarResult) 

    session.execute = AsyncMock(return_value=execute_result_sync_mock) # session.execute() is async
    execute_result_sync_mock.scalars = MagicMock(return_value=scalars_provider_async_mock) # .scalars() is sync

    _scalar_first_queue = []
    async def mock_scalar_first_side_effect():
        if _scalar_first_queue:
            return _scalar_first_queue.pop(0)
        return None
    scalars_provider_async_mock.first = AsyncMock(side_effect=mock_scalar_first_side_effect) # .first() is async

    def set_execute_scalar_first_results(*results):
        nonlocal _scalar_first_queue
        _scalar_first_queue = list(results)
    session.set_execute_scalar_first_results = set_execute_scalar_first_results
    
    session.get = AsyncMock(return_value=None) 
    session.merge = AsyncMock(side_effect=lambda instance: instance) 
    session.add = MagicMock() 
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

@pytest.fixture
def mock_user(mock_db_session: AsyncMock) -> User:
    user = User(
        id="user_test_123", 
        email="test@example.com",
        hashed_password="hashed_password",
        stripe_customer_id="cus_testcustomer"
    )
    user.is_active = True
    user.is_verified = True
    user.account_status = "active"
    user.has_consumed_initial_trial = False 
    return user

@pytest.fixture
def mock_subscription_model() -> MagicMock: 
    """Provides a mock Subscription object."""
    sub = MagicMock(spec=Subscription)
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
    
    def dict_to_magicmock(d_obj):
        if isinstance(d_obj, dict):
            m = MagicMock()
            m._original_dict_items = d_obj.copy()
            for k, v_item in d_obj.items():
                setattr(m, k, dict_to_magicmock(v_item))
            
            def mock_get(key, default=None):
                if hasattr(m, key) and not isinstance(getattr(m,key), MagicMock) and getattr(m,key) is not None :
                     return getattr(m, key)
                if key in m._original_dict_items:
                    return dict_to_magicmock(m._original_dict_items[key]) 
                return default
            m.get = MagicMock(side_effect=mock_get)
            return m
        elif isinstance(d_obj, list):
            return [dict_to_magicmock(item) for item in d_obj]
        return d_obj

    event.data.object = dict_to_magicmock(data_object)
    return event

# --- Test Classes ---

@pytest.mark.asyncio
class TestWebhookServiceEventProcessing:
    """Tests for event processing checks (is_event_processed, mark_event_as_processed)."""

    async def test_mark_event_as_processed_success(self, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_id = "evt_to_mark"
        event_type = "test.processing"
        
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
    @patch('app.services.webhook_service.isinstance') 
    async def test_get_fingerprint_from_payment_intent(self, mock_isinstance: MagicMock, mock_stripe_payment_intent: MagicMock, webhook_service: WebhookService):
        mock_isinstance.return_value = True 
        mock_pi = MagicMock()
        mock_pi.payment_method = MagicMock()
        mock_pi.payment_method.card = MagicMock()
        mock_pi.payment_method.card.fingerprint = "fingerprint_from_pi"
        mock_stripe_payment_intent.retrieve.return_value = mock_pi

        event_data = MagicMock()
        def get_side_effect(key, default=None):
            if key == "payment_intent": return "pi_123"
            if key == "setup_intent": return None
            if key == "default_payment_method": return None
            if key == "payment_method_details": return None
            return default
        event_data.get = MagicMock(side_effect=get_side_effect)
        
        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        
        assert fingerprint == "fingerprint_from_pi"
        mock_stripe_payment_intent.retrieve.assert_called_once_with("pi_123", expand=["payment_method"])

    @patch('app.services.webhook_service.stripe.SetupIntent')
    @patch('app.services.webhook_service.isinstance')
    async def test_get_fingerprint_from_setup_intent(self, mock_isinstance: MagicMock, mock_stripe_setup_intent: MagicMock, webhook_service: WebhookService):
        mock_isinstance.return_value = True
        mock_si = MagicMock()
        mock_si.payment_method = MagicMock()
        mock_si.payment_method.card = MagicMock()
        mock_si.payment_method.card.fingerprint = "fingerprint_from_si"
        mock_stripe_setup_intent.retrieve.return_value = mock_si

        event_data = MagicMock()
        def get_side_effect(key, default=None):
            if key == "payment_intent": return None
            if key == "setup_intent": return "si_123"
            if key == "default_payment_method": return None
            if key == "payment_method_details": return None
            return default
        event_data.get = MagicMock(side_effect=get_side_effect)

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
        def get_side_effect(key, default=None):
            if key == "payment_intent": return None
            if key == "setup_intent": return None
            if key == "default_payment_method": return "pm_123"
            if key == "payment_method_details": return None
            return default
        event_data.get = MagicMock(side_effect=get_side_effect)


        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "fingerprint_from_dpm"
        mock_stripe_payment_method.retrieve.assert_called_once_with("pm_123")

    async def test_get_fingerprint_from_event_data_direct(self, webhook_service: WebhookService):
        event_data = MagicMock()
        payment_method_details_mock = {"card": {"fingerprint": "direct_fingerprint"}}
        
        def get_side_effect(key, default=None): 
            if key == "payment_intent": return None
            if key == "setup_intent": return None
            if key == "default_payment_method": return None
            if key == "payment_method_details": return payment_method_details_mock
            return default if default is not None else {} 
        event_data.get = MagicMock(side_effect=get_side_effect)
        
        fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_test")
        assert fingerprint == "direct_fingerprint"

    @patch('app.services.webhook_service.stripe.PaymentIntent')
    async def test_get_fingerprint_stripe_error(self, mock_stripe_payment_intent: MagicMock, webhook_service: WebhookService, mock_logger: MagicMock):
        mock_stripe_payment_intent.retrieve.side_effect = stripe.error.StripeError("Stripe API Down")
        
        event_data = MagicMock()
        def get_side_effect(key, default=None):
            if key == "payment_intent": return "pi_error"
            return None
        event_data.get = MagicMock(side_effect=get_side_effect)


        with patch('app.services.webhook_service.logger', mock_logger):
            fingerprint = await webhook_service.get_card_fingerprint_from_event(event_data, "evt_stripe_err")
        
        assert fingerprint is None
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger') 
class TestHandleCheckoutSessionCompleted:
    """Tests for handle_checkout_session_completed."""

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
        webhook_service.db.execute.assert_not_called() 

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_no_card_fingerprint_logs_warning_and_returns(
        self, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock
    ):
        mock_get_fingerprint.return_value = None
        event_payload = {
            "id": "cs_test_no_fp",
            "client_reference_id": "user_123", 
            "customer": "cus_test_customer",
            "subscription": "sub_test_subscription",
            "metadata": {"user_id": "user_123"}
        }
        event = create_stripe_event_payload(event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_logger.warning.assert_called_with(
            f"Card fingerprint not found for checkout.session.completed: {event.id}. Cannot perform trial uniqueness check.",
            event_id=event.id
        )
        mock_db_session.execute.assert_not_called() 

    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription') 
    async def test_unique_fingerprint_proceeds_normally(
        self, mock_stripe_sub_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock, mock_user: User
    ):
        card_fingerprint = "fp_unique_card_checkout"
        user_id = mock_user.id
        event_id = "evt_checkout_unique_proceed"
        
        mock_get_fingerprint.return_value = card_fingerprint
        mock_db_session.set_execute_scalar_first_results(None) 
        mock_db_session.get.return_value = mock_user 

        event_payload = {
            "id": "cs_unique_proceed", "client_reference_id": user_id, "customer": "cus_unique", 
            "subscription": "sub_unique_proceed", "metadata": {"user_id": user_id}
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once()
        mock_stripe_sub_api.delete.assert_not_called()
        mock_event_publisher.publish_user_trial_blocked.assert_not_called()
        mock_logger.info.assert_any_call( 
            f"Card fingerprint {card_fingerprint} processing for trial. User ID {user_id}. Duplication check disabled.",
            event_id=event_id, user_id=user_id, card_fingerprint=card_fingerprint
        )
        calls_to_execute = [
            c for c in mock_db_session.execute.call_args_list 
            if isinstance(c[0][0], Select) and UsedTrialCardFingerprint in [desc['entity'] for desc in c[0][0].column_descriptions]
        ]
        assert not calls_to_execute, "DB execute should not be called for fingerprint check"


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription.delete') 
    async def test_formerly_duplicate_fingerprint_proceeds_normally(
        self, mock_stripe_sub_delete_api: MagicMock, mock_get_fingerprint: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, mock_event_publisher: MagicMock, mock_user: User
    ):
        card_fingerprint = "fp_formerly_duplicate_card_checkout"
        user_id = mock_user.id
        stripe_customer_id = "cus_formerly_dup"
        stripe_subscription_id = "sub_formerly_dup_proceed"
        event_id = "evt_checkout_formerly_dup_proceed"
        
        mock_get_fingerprint.return_value = card_fingerprint
        mock_db_session.get.return_value = mock_user 

        event_payload = {
            "id": "cs_formerly_dup_proceed", "client_reference_id": user_id, 
            "customer": stripe_customer_id, "subscription": stripe_subscription_id, 
            "metadata": {"user_id": user_id}
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="checkout.session.completed", data_object=event_payload)

        await webhook_service.handle_checkout_session_completed(event)

        mock_get_fingerprint.assert_called_once()
        mock_stripe_sub_delete_api.assert_not_called() 
        mock_event_publisher.publish_user_trial_blocked.assert_not_called() 
        assert mock_user.account_status != "trial_rejected" 
        mock_logger.info.assert_any_call(
            f"Card fingerprint {card_fingerprint} processing for trial. User ID {user_id}. Duplication check disabled.",
            event_id=event_id, user_id=user_id, card_fingerprint=card_fingerprint
        )
        calls_to_execute = [
            c for c in mock_db_session.execute.call_args_list 
            if isinstance(c[0][0], Select) and UsedTrialCardFingerprint in [desc['entity'] for desc in c[0][0].column_descriptions]
        ]
        assert not calls_to_execute, "DB execute should not be called for fingerprint check"


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger') 
@patch('app.services.webhook_service.get_or_create_subscription', new_callable=AsyncMock)
class TestHandleCustomerSubscriptionCreated:
    """Tests for handle_customer_subscription_created."""

    async def test_no_user_id_logs_error_and_returns(
        self, mock_get_or_create_sub: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock
    ):
        event_payload = {
            "id": "sub_no_user_created", "customer": "cus_no_user_mapping", 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_test"}}]},
            "metadata": {}, 
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.created", data_object=event_payload)
        mock_db_session.set_execute_scalar_first_results(None) # User not found by stripe_customer_id

        await webhook_service.handle_customer_subscription_created(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for customer.subscription.created: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_get_or_create_sub.assert_not_called()


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_no_card_fingerprint_raises_value_error(
        self, mock_get_fingerprint: AsyncMock, mock_get_or_create_sub: AsyncMock, 
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_user: User
    ):
        mock_get_fingerprint.return_value = None
        stripe_subscription_id = "sub_no_fp_trial"
        event_payload = {
            "id": stripe_subscription_id, "customer": mock_user.stripe_customer_id, 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_trial"}}]},
            "metadata": {"user_id": mock_user.id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.created", data_object=event_payload)
        
        mock_db_session.get.return_value = mock_user 

        with pytest.raises(ValueError, match=f"Card fingerprint missing for trial subscription {stripe_subscription_id}"):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_db_session.rollback.assert_called_once() 
        mock_get_or_create_sub.assert_not_called() 


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    @patch('app.services.webhook_service.stripe.Subscription.delete') 
    async def test_trialing_sub_duplicate_fingerprint_proceeds_as_unique( 
        self, mock_stripe_sub_delete_api: MagicMock, mock_get_fingerprint: AsyncMock, 
        mock_get_or_create_sub: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, 
        mock_event_publisher: MagicMock, mock_user: User, mock_subscription_model: MagicMock
    ):
        card_fingerprint = "fp_duplicate_but_allowed_service"
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_subscription_id = f"sub_dup_as_unique_service_{datetime.now().timestamp()}"
        event_id = "evt_sub_created_dup_as_unique_service"
        trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
        trial_end_date_obj = datetime.fromtimestamp(trial_end_ts, timezone.utc)
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = trial_end_ts


        mock_get_fingerprint.return_value = card_fingerprint
        
        mock_user.has_consumed_initial_trial = False 
        mock_user.account_status = "active" 
        mock_db_session.get.return_value = mock_user
        
        mock_subscription_model.user_id = user_id
        mock_subscription_model.stripe_subscription_id = stripe_subscription_id
        mock_subscription_model.stripe_customer_id = stripe_customer_id
        mock_subscription_model.status = "unknown" 
        mock_get_or_create_sub.return_value = mock_subscription_model

        mock_db_session.set_execute_scalar_first_results(None) # For UserCredit select
        
        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock() 
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()


        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_dup_service"}}]},
            "metadata": {"user_id": user_id}, "trial_end": trial_end_ts,
            "default_payment_method": "pm_some_default_method_dup_service",
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        await webhook_service.handle_customer_subscription_created(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        
        mock_event_publisher.publish_user_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_date_obj,
            credits_granted=settings.FREE_TRIAL_CREDITS
        )
        mock_event_publisher.publish_user_trial_blocked.assert_not_called()
        mock_stripe_sub_delete_api.assert_not_called() 

        assert mock_user.account_status == "trialing"
        assert mock_user.has_consumed_initial_trial is True

        added_uc_instance = None
        added_ct_instance = None
        added_fingerprint_instance = None

        assert mock_db_session.add.called
        for call_args in mock_db_session.add.call_args_list:
            instance = call_args[0][0]
            if isinstance(instance, UserCredit): added_uc_instance = instance
            elif isinstance(instance, CreditTransaction): added_ct_instance = instance
            elif isinstance(instance, UsedTrialCardFingerprint): added_fingerprint_instance = instance
        
        assert added_fingerprint_instance is None, "UsedTrialCardFingerprint should not be added"
        assert added_uc_instance is not None, "UserCredit not added"
        if added_uc_instance:
            assert added_uc_instance.balance == settings.FREE_TRIAL_CREDITS
        assert added_ct_instance is not None, "CreditTransaction not added"
        if added_ct_instance:
            assert added_ct_instance.amount == settings.FREE_TRIAL_CREDITS
            assert added_ct_instance.transaction_type == TransactionType.TRIAL_CREDIT_GRANT

        mock_db_session.commit.assert_called_once()
        mock_db_session.rollback.assert_not_called()


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_unique_fingerprint_grants_credits_updates_user_publishes_event(
        self, mock_get_fingerprint: AsyncMock, mock_get_or_create_sub: AsyncMock, 
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, 
        mock_event_publisher: MagicMock, mock_user: User, mock_subscription_model: MagicMock
    ):
        card_fingerprint = "fp_unique_card_trial_service"
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_subscription_id = f"sub_unique_trial_service_{datetime.now().timestamp()}"
        event_id = "evt_sub_created_unique_trial_service"
        trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
        trial_end_date_obj = datetime.fromtimestamp(trial_end_ts, timezone.utc)
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = trial_end_ts

        mock_get_fingerprint.return_value = card_fingerprint
        
        mock_user.has_consumed_initial_trial = False
        mock_user.account_status = "active" 
        mock_db_session.get.return_value = mock_user
        
        mock_subscription_model.user_id = user_id
        mock_subscription_model.stripe_subscription_id = stripe_subscription_id
        mock_subscription_model.stripe_customer_id = stripe_customer_id
        mock_subscription_model.status = "unknown"
        mock_get_or_create_sub.return_value = mock_subscription_model
        
        mock_db_session.set_execute_scalar_first_results(None) # For UserCredit select
        
        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_unique_service"}}]},
            "metadata": {"user_id": user_id}, "trial_end": trial_end_ts,
            "default_payment_method": "pm_default_unique_trial_service",
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        await webhook_service.handle_customer_subscription_created(event)

        mock_get_fingerprint.assert_called_once_with(event.data.object, event.id)
        mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
        
        mock_event_publisher.publish_user_trial_started.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            trial_end_date=trial_end_date_obj,
            credits_granted=settings.FREE_TRIAL_CREDITS
        )
        mock_event_publisher.publish_user_trial_blocked.assert_not_called()

        assert mock_user.has_consumed_initial_trial is True
        assert mock_user.account_status == "trialing"

        added_uc_instance = None
        added_ct_instance = None
        added_fingerprint_instance = None

        assert mock_db_session.add.called
        for call_args in mock_db_session.add.call_args_list:
            instance = call_args[0][0]
            if isinstance(instance, UserCredit): added_uc_instance = instance
            elif isinstance(instance, CreditTransaction): added_ct_instance = instance
            elif isinstance(instance, UsedTrialCardFingerprint): added_fingerprint_instance = instance
        
        assert added_fingerprint_instance is None, "UsedTrialCardFingerprint should not be added"
        assert added_uc_instance is not None, "UserCredit not added"
        if added_uc_instance:
            assert added_uc_instance.balance == settings.FREE_TRIAL_CREDITS
        assert added_ct_instance is not None, "CreditTransaction not added"
        if added_ct_instance:
            assert added_ct_instance.amount == settings.FREE_TRIAL_CREDITS
            assert added_ct_instance.transaction_type == TransactionType.TRIAL_CREDIT_GRANT
            assert added_ct_instance.reference_id == stripe_subscription_id

        mock_db_session.commit.assert_called_once()
        mock_db_session.rollback.assert_not_called()


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_trialing_sub_user_already_consumed_trial(
        self, mock_get_fingerprint: AsyncMock, mock_get_or_create_sub: AsyncMock, 
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, 
        mock_event_publisher: MagicMock, mock_user: User, mock_subscription_model: MagicMock
    ):
        card_fingerprint = "fp_consumed_trial_service"
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_subscription_id = "sub_consumed_trial_service"
        event_id = "evt_sub_created_consumed_trial_service"
        trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = trial_end_ts


        mock_get_fingerprint.return_value = card_fingerprint
        
        mock_user.has_consumed_initial_trial = True 
        mock_user.account_status = "active"
        mock_db_session.get.return_value = mock_user
        
        mock_subscription_model.user_id = user_id
        mock_subscription_model.stripe_subscription_id = stripe_subscription_id
        mock_get_or_create_sub.return_value = mock_subscription_model
        
        mock_db_session.add = MagicMock()
        mock_db_session.commit = AsyncMock()


        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_trial_consumed_service"}}]},
            "metadata": {"user_id": user_id}, "trial_end": trial_end_ts,
            "default_payment_method": "pm_consumed_trial_service",
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_id=event_id, event_type="customer.subscription.created", data_object=event_payload)

        await webhook_service.handle_customer_subscription_created(event)

        mock_event_publisher.publish_user_trial_started.assert_not_called()
        mock_event_publisher.publish_user_trial_blocked.assert_not_called()
        
        assert not any(isinstance(call.args[0], UserCredit) for call in mock_db_session.add.call_args_list)
        assert not any(isinstance(call.args[0], CreditTransaction) for call in mock_db_session.add.call_args_list)
        assert not any(isinstance(call.args[0], UsedTrialCardFingerprint) for call in mock_db_session.add.call_args_list)

        assert mock_user.account_status == "trialing" 
        mock_db_session.commit.assert_called_once() 


    async def test_db_error_during_subscription_update_create_rolls_back_and_raises(
        self, mock_get_or_create_sub: AsyncMock, # Added from class patch
        mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User
    ):
        user_id = mock_user.id
        stripe_subscription_id = "sub_db_error_create_service"
        event_payload = {
            "id": stripe_subscription_id, "customer": mock_user.stripe_customer_id, 
            "status": "active", "items": {"data": [{"price": {"id": "price_db_error_service"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.created", data_object=event_payload)

        mock_db_session.get.return_value = mock_user 
        
        # Configure the mock_get_or_create_sub (which is already an AsyncMock from class patch)
        db_subscription_mock = MagicMock(spec=Subscription) 
        mock_get_or_create_sub.return_value = db_subscription_mock

        # Simulate error during merge
        mock_db_session.merge.side_effect = SQLAlchemyError("DB merge boom service")

        with pytest.raises(SQLAlchemyError, match="DB merge boom service"):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()


    @patch('app.services.webhook_service.WebhookService.get_card_fingerprint_from_event', new_callable=AsyncMock)
    async def test_final_db_commit_error_rolls_back_and_raises(
        self, mock_get_fingerprint: AsyncMock, mock_get_or_create_sub: AsyncMock, 
        mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, 
        mock_user: User, mock_subscription_model: MagicMock, mock_event_publisher: MagicMock
    ):
        user_id = "user_final_commit_err_service"
        stripe_subscription_id = "sub_final_commit_err_service"
        card_fingerprint = "fp_final_commit_err_service"
        trial_end_ts = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp())
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = trial_end_ts


        mock_get_fingerprint.return_value = card_fingerprint
        
        mock_user_obj = MagicMock(spec=User)
        mock_user_obj.id = user_id
        mock_user_obj.has_consumed_initial_trial = False
        mock_user_obj.account_status = "active"
        mock_user_obj.stripe_customer_id = "cus_final_commit_err_service"
        mock_db_session.get.return_value = mock_user_obj
        
        mock_subscription_model.user_id = user_id
        mock_subscription_model.stripe_subscription_id = stripe_subscription_id
        mock_get_or_create_sub.return_value = mock_subscription_model
        
        mock_db_session.set_execute_scalar_first_results(None) 
        mock_db_session.commit.side_effect = SQLAlchemyError("Final commit boom service")
        mock_db_session.add = MagicMock() 
        mock_db_session.flush = AsyncMock()


        event_payload = {
            "id": stripe_subscription_id, "customer": mock_user_obj.stripe_customer_id, 
            "status": "trialing", "items": {"data": [{"price": {"id": "price_final_commit_err_service"}}]},
            "metadata": {"user_id": user_id}, "trial_end": trial_end_ts,
            "default_payment_method": "pm_final_commit_err_service",
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.created", data_object=event_payload)

        with pytest.raises(SQLAlchemyError, match="Final commit boom service"):
            await webhook_service.handle_customer_subscription_created(event)
        
        mock_db_session.rollback.assert_called_once()
        mock_event_publisher.publish_user_trial_started.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleCustomerSubscriptionUpdated:
    """Tests for handle_customer_subscription_updated."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "sub_updated_no_user", "customer": "cus_no_user_map_upd", 
            "status": "active", "metadata": {},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()), 
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)
        mock_db_session.set_execute_scalar_first_results(None) # User not found by stripe_customer_id

        await webhook_service.handle_customer_subscription_updated(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for customer.subscription.updated: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        assert mock_db_session.execute.call_count == 1 


    @patch("app.services.webhook_service.get_or_create_subscription", new_callable=AsyncMock)
    async def test_local_subscription_not_found_creates_one_and_updates(
        self, mock_get_or_create_sub: AsyncMock, mock_logger: MagicMock, 
        webhook_service: WebhookService, mock_db_session: AsyncMock, 
        mock_user: User, mock_subscription_model: MagicMock, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_subscription_id = "sub_updated_new_local"
        stripe_customer_id = mock_user.stripe_customer_id
        new_stripe_status = "active"
        new_price_id = "price_updated_plan"
        current_period_start_ts = int(datetime.now(timezone.utc).timestamp())
        current_period_end_ts = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())


        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": new_stripe_status, 
            "items": {"data": [{"price": {"id": new_price_id}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": current_period_start_ts,
            "current_period_end": current_period_end_ts,
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_db_session.set_execute_scalar_first_results(None) # Local sub not found
        
        mock_subscription_model.user_id = user_id
        mock_subscription_model.stripe_subscription_id = stripe_subscription_id
        mock_subscription_model.stripe_customer_id = None 
        mock_subscription_model.status = "initial_unknown" 
        mock_subscription_model.stripe_price_id = "old_price"
        mock_get_or_create_sub.return_value = mock_subscription_model
        
        original_user_status = "pending" 
        mock_user.account_status = original_user_status
        mock_db_session.get.return_value = mock_user
        mock_db_session.commit = AsyncMock()


        await webhook_service.handle_customer_subscription_updated(event)

        mock_get_or_create_sub.assert_called_once_with(webhook_service.db, user_id, stripe_subscription_id)
        
        assert mock_subscription_model.status == new_stripe_status
        assert mock_subscription_model.stripe_price_id == new_price_id
        assert mock_subscription_model.stripe_customer_id == stripe_customer_id 
        assert mock_subscription_model.current_period_start == datetime.fromtimestamp(current_period_start_ts, timezone.utc)
        assert mock_subscription_model.current_period_end == datetime.fromtimestamp(current_period_end_ts, timezone.utc)
        assert mock_subscription_model.cancel_at_period_end is False


        assert mock_user.account_status == new_stripe_status 
        mock_db_session.commit.assert_called_once()
        if original_user_status == "frozen" and new_stripe_status == "active":
             mock_event_publisher.publish_user_account_unfrozen.assert_called_once()
        else:
            mock_event_publisher.publish_user_account_unfrozen.assert_not_called()
        mock_event_publisher.publish_user_account_frozen.assert_not_called()


    async def test_status_change_active_to_frozen_publishes_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_subscription_id = "sub_active_to_frozen"
        stripe_customer_id = mock_user.stripe_customer_id
        
        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": "past_due", "items": {"data": [{"price": {"id": "price_active_frozen"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_user.account_status = "active" 
        mock_db_session.get.return_value = mock_user
        
        mock_local_sub = MagicMock(spec=Subscription)
        mock_local_sub.status = "active"
        mock_db_session.set_execute_scalar_first_results(mock_local_sub) # For select(Subscription)
        mock_db_session.commit = AsyncMock()


        await webhook_service.handle_customer_subscription_updated(event)

        assert mock_user.account_status == "frozen"
        mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )
        mock_db_session.commit.assert_called_once()

    async def test_status_change_frozen_to_active_publishes_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_subscription_id = "sub_frozen_to_active"
        stripe_customer_id = mock_user.stripe_customer_id

        event_payload = {
            "id": stripe_subscription_id, "customer": stripe_customer_id, 
            "status": "active", "items": {"data": [{"price": {"id": "price_frozen_active"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_user.account_status = "frozen" 
        mock_db_session.get.return_value = mock_user
        
        mock_local_sub = MagicMock(spec=Subscription)
        mock_local_sub.status = "past_due"
        mock_db_session.set_execute_scalar_first_results(mock_local_sub) # For select(Subscription)
        mock_db_session.commit = AsyncMock()

        await webhook_service.handle_customer_subscription_updated(event)

        assert mock_user.account_status == "active"
        mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="subscription_status_change"
        )
        mock_db_session.commit.assert_called_once()


    async def test_user_not_found_logs_error_rolls_back(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id = "non_existent_user_update"
        stripe_subscription_id = "sub_user_not_found_update_service"
        event_payload = {
            "id": stripe_subscription_id, "customer": "cus_user_not_found_update", 
            "status": "active", "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_db_session.set_execute_scalar_first_results(MagicMock(spec=Subscription)) # Found a subscription
        mock_db_session.get.return_value = None # But user not found

        await webhook_service.handle_customer_subscription_updated(event)
        
        mock_logger.error.assert_any_call(
            f"User {user_id} not found when updating account status for subscription {stripe_subscription_id}.",
            event_id=event.id, user_id=user_id
        )
        mock_db_session.rollback.assert_called_once() 
        mock_db_session.commit.assert_not_called()


    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_user: User):
        user_id = "user_db_commit_err_sub_update_service"
        stripe_subscription_id = "sub_db_commit_err_service"
        
        event_payload = {
            "id": stripe_subscription_id, "customer": mock_user.stripe_customer_id, 
            "status": "active", "items": {"data": [{"price": {"id": "price_db_commit_err_service"}}]},
            "metadata": {"user_id": user_id},
            "current_period_start": int(datetime.now(timezone.utc).timestamp()),
            "current_period_end": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
            "cancel_at_period_end": False
        }
        event = create_stripe_event_payload(event_type="customer.subscription.updated", data_object=event_payload)

        mock_user.account_status = "pending"
        mock_db_session.get.return_value = mock_user
        
        mock_local_sub = MagicMock(spec=Subscription)
        mock_local_sub.status = "pending"
        mock_db_session.set_execute_scalar_first_results(mock_local_sub) # For select(Subscription)
        
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed sub update")

        with pytest.raises(SQLAlchemyError, match="DB commit failed sub update"):
            await webhook_service.handle_customer_subscription_updated(event)
        
        mock_db_session.rollback.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentSucceeded:
    """Tests for handle_invoice_payment_succeeded."""

    # async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
    #     event_payload = {
    #         "id": "in_no_user_succeeded_service", "customer": "cus_no_user_map_inv_succ_service", 
    #         "subscription": None, "paid": True, "status": "paid",
    #         "customer_details": {"metadata": {}}, 
    #         "amount_paid": 1000, "currency": "usd", "billing_reason": "manual", "invoice_pdf": None
    #     }
    #     event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
    #     mock_db_session.set_execute_scalar_first_results(None) # User not found by stripe_customer_id

    #     await webhook_service.handle_invoice_payment_succeeded(event)
        
    #     mock_logger.error.assert_called_with(
    #         f"User ID not found for invoice.payment_succeeded: {event.id}, Stripe Customer: {event.data.object.customer}",
    #         event_id=event.id, stripe_customer_id=event.data.object.customer
    #     )
    #     mock_db_session.commit.assert_not_called()


    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id_from_meta = "ghost_user_id_succ_service"
        event_payload = {
            "id": "in_user_not_found_succ_service", "customer": "cus_ghost_user_succ_service", 
            "subscription": None, "paid": True, "status": "paid",
            "customer_details": {"metadata": {"user_id": user_id_from_meta}},
            "amount_paid": 1000, "currency": "usd", "billing_reason": "manual", "invoice_pdf": None
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)
        mock_db_session.get.return_value = None 

        await webhook_service.handle_invoice_payment_succeeded(event)
        
        mock_logger.error.assert_called_with(
            f"User {user_id_from_meta} not found for invoice.payment_succeeded: {event.id}",
            event_id=event.id, user_id=user_id_from_meta
        )
        mock_db_session.commit.assert_not_called()


    async def test_payment_succeeded_updates_user_publishes_events(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_subscription_id = "sub_inv_succ_service_123"
        stripe_invoice_id = "in_inv_succ_service_123"
        amount_paid = 2000
        currency = "usd"
        billing_reason = "subscription_cycle"
        invoice_pdf_url = "https://example.com/invoice_succ_service.pdf"

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, 
            "subscription": stripe_subscription_id, "paid": True, "status": "paid",
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": amount_paid, "currency": currency, 
            "billing_reason": billing_reason, "invoice_pdf": invoice_pdf_url
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user.account_status = "frozen" 
        mock_db_session.get.return_value = mock_user
        
        mock_local_sub = MagicMock(spec=Subscription)
        mock_local_sub.status = "past_due"
        mock_db_session.set_execute_scalar_first_results(mock_local_sub) # For select(Subscription)
        mock_db_session.commit = AsyncMock()


        await webhook_service.handle_invoice_payment_succeeded(event)

        assert mock_user.account_status == "active"
        assert mock_local_sub.status == "active" 
        
        mock_event_publisher.publish_user_invoice_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            amount_paid=amount_paid,
            currency=currency,
            billing_reason=billing_reason,
            invoice_pdf_url=invoice_pdf_url
        )
        mock_event_publisher.publish_user_account_unfrozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="invoice_paid_after_failure"
        )
        mock_db_session.commit.assert_called_once()


    async def test_payment_succeeded_no_subscription_updates_user_publishes_invoice_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_invoice_id = "in_inv_succ_no_sub_service"
        amount_paid = 500
        currency = "eur"
        billing_reason = "manual" 
        invoice_pdf_url = "https://example.com/invoice_no_sub_service.pdf"

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, 
            "subscription": None, "paid": True, "status": "paid",
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": amount_paid, "currency": currency, 
            "billing_reason": billing_reason, "invoice_pdf": invoice_pdf_url
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user.account_status = "active" 
        mock_db_session.get.return_value = mock_user
        mock_db_session.commit = AsyncMock()

        await webhook_service.handle_invoice_payment_succeeded(event)

        assert mock_user.account_status == "active" 
        
        mock_event_publisher.publish_user_invoice_paid.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=None,
            stripe_invoice_id=stripe_invoice_id,
            amount_paid=amount_paid,
            currency=currency,
            billing_reason=billing_reason,
            invoice_pdf_url=invoice_pdf_url
        )
        mock_event_publisher.publish_user_account_unfrozen.assert_not_called()
        mock_db_session.commit.assert_called_once() 


    async def test_db_commit_error_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_user: User):
        user_id = "user_db_commit_err_inv_succ_service"
        event_payload = {
            "id": "in_db_commit_err_service", "customer": mock_user.stripe_customer_id, 
            "subscription": "sub_db_commit_err_service", "paid": True, "status": "paid",
            "customer_details": {"metadata": {"user_id": user_id}},
            "amount_paid": 100, "currency": "usd", "billing_reason": "test", "invoice_pdf": None
        }
        event = create_stripe_event_payload(event_type="invoice.payment_succeeded", data_object=event_payload)

        mock_user_obj = MagicMock(spec=User); mock_user_obj.id = user_id; mock_user_obj.account_status = "pending"
        mock_db_session.get.return_value = mock_user_obj
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed inv succ")

        with pytest.raises(SQLAlchemyError, match="DB commit failed inv succ"):
            await webhook_service.handle_invoice_payment_succeeded(event)
        
        mock_db_session.rollback.assert_called_once()


@pytest.mark.asyncio
@patch('app.services.webhook_service.logger')
class TestHandleInvoicePaymentFailed:
    """Tests for handle_invoice_payment_failed."""

    async def test_no_user_id_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        event_payload = {
            "id": "in_no_user_failed_service", "customer": "cus_no_user_map_inv_fail_service", 
            "subscription": None, "paid": False, "status": "open",
            "customer_details": {"metadata": {}},
            "charge": None, "last_payment_error": None, "next_payment_attempt": None
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.set_execute_scalar_first_results(None) # User not found by stripe_customer_id

        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_logger.error.assert_called_with(
            f"User ID not found for invoice.payment_failed: {event.id}, Stripe Customer: {event.data.object.customer}",
            event_id=event.id, stripe_customer_id=event.data.object.customer
        )
        mock_db_session.commit.assert_not_called()


    async def test_user_not_found_logs_error_and_returns(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock):
        user_id_from_meta = "ghost_user_id_fail_service"
        event_payload = {
            "id": "in_user_not_found_fail_service", "customer": "cus_ghost_user_fail_service", 
            "subscription": None, "paid": False, "status": "open",
            "customer_details": {"metadata": {"user_id": user_id_from_meta}},
            "charge": None, "last_payment_error": None, "next_payment_attempt": None
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)
        mock_db_session.get.return_value = None 

        await webhook_service.handle_invoice_payment_failed(event)
        
        mock_logger.error.assert_called_with(
            f"User {user_id_from_meta} not found for invoice.payment_failed: {event.id}",
            event_id=event.id, user_id=user_id_from_meta
        )
        mock_db_session.commit.assert_not_called()


    async def test_payment_failed_for_subscription_freezes_user_publishes_events(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_subscription_id = "sub_inv_fail_service_123"
        stripe_invoice_id = "in_inv_fail_service_123"
        charge_id = "ch_failed_charge_service"
        failure_message = "Your card was declined (service test)."
        next_attempt_ts = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, 
            "subscription": stripe_subscription_id, "paid": False, "status": "open",
            "customer_details": {"metadata": {"user_id": user_id}},
            "billing_reason": "subscription_cycle",
            "charge": charge_id,
            "last_payment_error": {"message": failure_message},
            "next_payment_attempt": next_attempt_ts
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)

        mock_user.account_status = "active" 
        mock_db_session.get.return_value = mock_user
        
        mock_local_sub = MagicMock(spec=Subscription) 
        mock_local_sub.status = "active"
        mock_db_session.set_execute_scalar_first_results(mock_local_sub) # For select(Subscription)
        mock_db_session.commit = AsyncMock()


        await webhook_service.handle_invoice_payment_failed(event)

        assert mock_user.account_status == "frozen"
        
        mock_event_publisher.publish_user_invoice_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=stripe_invoice_id,
            stripe_charge_id=charge_id,
            failure_reason=failure_message,
            next_payment_attempt_date=datetime.fromtimestamp(next_attempt_ts, timezone.utc)
        )
        mock_event_publisher.publish_user_account_frozen.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            reason="invoice_payment_failed"
        )
        mock_db_session.commit.assert_called_once()


    async def test_payment_failed_non_subscription_no_freeze_publishes_invoice_event(
        self, mock_logger: MagicMock, webhook_service: WebhookService, 
        mock_db_session: AsyncMock, mock_user: User, mock_event_publisher: MagicMock
    ):
        user_id = mock_user.id
        stripe_customer_id = mock_user.stripe_customer_id
        stripe_invoice_id = "in_inv_fail_non_sub_service"
        charge_id = "ch_failed_charge_non_sub_service"
        failure_message = "Payment failed for one-time item (service test)."

        event_payload = {
            "id": stripe_invoice_id, "customer": stripe_customer_id, 
            "subscription": None, "paid": False, "status": "open",
            "customer_details": {"metadata": {"user_id": user_id}},
            "billing_reason": "manual", 
            "charge": charge_id,
            "last_payment_error": {"message": failure_message},
            "next_payment_attempt": None
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)

        mock_user.account_status = "active"
        mock_db_session.get.return_value = mock_user
        mock_db_session.commit = AsyncMock()

        await webhook_service.handle_invoice_payment_failed(event)

        assert mock_user.account_status == "active" 
        
        mock_event_publisher.publish_user_invoice_failed.assert_called_once_with(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=None,
            stripe_invoice_id=stripe_invoice_id,
            stripe_charge_id=charge_id,
            failure_reason=failure_message,
            next_payment_attempt_date=None
        )
        mock_event_publisher.publish_user_account_frozen.assert_not_called()
        mock_db_session.commit.assert_not_called() 


    async def test_db_commit_error_if_needed_rolls_back_and_raises(self, mock_logger: MagicMock, webhook_service: WebhookService, mock_db_session: AsyncMock, mock_user: User):
        user_id = "user_db_commit_err_inv_fail_service"
        event_payload = {
            "id": "in_db_commit_err_fail_service", "customer": mock_user.stripe_customer_id, 
            "subscription": "sub_db_commit_err_fail_service", "paid": False, "status": "open",
            "customer_details": {"metadata": {"user_id": user_id}},
            "billing_reason": "subscription_cycle",
            "charge": "ch_db_err_service", 
            "last_payment_error": {"message": "some error service"},
            "next_payment_attempt": None 
        }
        event = create_stripe_event_payload(event_type="invoice.payment_failed", data_object=event_payload)

        mock_user_obj = MagicMock(spec=User); mock_user_obj.id = user_id; mock_user_obj.account_status = "active"
        mock_db_session.get.return_value = mock_user_obj
        
        mock_db_session.set_execute_scalar_first_results(MagicMock(spec=Subscription)) # For select(Subscription)
        
        mock_db_session.commit.side_effect = SQLAlchemyError("DB commit failed on invoice fail service")

        with pytest.raises(SQLAlchemyError, match="DB commit failed on invoice fail service"):
            await webhook_service.handle_invoice_payment_failed(event)
        
        mock_db_session.rollback.assert_called_once()