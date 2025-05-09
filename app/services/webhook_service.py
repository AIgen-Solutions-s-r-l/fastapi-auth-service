import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import func, exists

from app.core.config import settings
from app.log.logging import logger
from app.models.user import User
from app.models.plan import UsedTrialCardFingerprint, Subscription
from app.models.processed_event import ProcessedStripeEvent
from app.models.credit import UserCredit, CreditTransaction, TransactionType # New imports
from app.core.db_utils import get_or_create_subscription # Helper for subscription
# from app.services.user_service import UserService # To update user status
# from app.services.credit_service import CreditService # To grant credits
from app.services.internal_event_publisher import InternalEventPublisher # To publish events
from datetime import datetime, timezone # For trial_end_date

stripe.api_key = settings.STRIPE_SECRET_KEY


class WebhookService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        # self.user_service = UserService(db_session)
        # self.credit_service = CreditService(db_session)
        self.event_publisher = InternalEventPublisher() # Assuming it doesn't need db session

    async def is_event_processed(self, event_id: str) -> bool:
        """Checks if a Stripe event has already been processed."""
        try:
            # Use exists() for a simple boolean check without fetching the entire object
            stmt = select(exists().where(ProcessedStripeEvent.stripe_event_id == event_id))
            result = await self.db.execute(stmt)
            # scalar() returns the first column of the first row directly
            return result.scalar()
        except Exception as e:
            logger.error(f"Error checking if event {event_id} was processed: {e}", event_id=event_id, exc_info=True)
            # In case of error, assume event was not processed to allow retry
            return False

    async def mark_event_as_processed(self, event_id: str, event_type: str):
        """Marks a Stripe event as processed."""
        try:
            stmt = pg_insert(ProcessedStripeEvent).values(
                stripe_event_id=event_id,
                event_type=event_type
            ).on_conflict_do_nothing(index_elements=['stripe_event_id'])
            await self.db.execute(stmt)
            await self.db.commit()
            logger.info(f"Marked event {event_id} ({event_type}) as processed.", event_id=event_id, event_type=event_type)
        except IntegrityError: # Should be caught by on_conflict_do_nothing, but as a safeguard
            await self.db.rollback()
            logger.warning(f"Event {event_id} already marked as processed (concurrent attempt?).", event_id=event_id)
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Database error marking event {event_id} as processed: {e}", event_id=event_id, exc_info=True)
            raise # Re-raise to be handled by the endpoint

    async def get_card_fingerprint_from_event(self, event_data_object: stripe.StripeObject, event_id_for_logging: str) -> str | None:
        """
        Retrieves card fingerprint from a Stripe event's data object.
        Handles different ways fingerprint might be available (PaymentIntent, SetupIntent, default_payment_method on Subscription).
        """
        fingerprint = None
        payment_intent_id = event_data_object.get("payment_intent")
        setup_intent_id = event_data_object.get("setup_intent")
        default_payment_method_id = event_data_object.get("default_payment_method")

        try:
            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
                if payment_intent.payment_method and isinstance(payment_intent.payment_method, stripe.PaymentMethod) and payment_intent.payment_method.card:
                    fingerprint = payment_intent.payment_method.card.fingerprint
            elif setup_intent_id:
                setup_intent = stripe.SetupIntent.retrieve(setup_intent_id, expand=["payment_method"])
                if setup_intent.payment_method and isinstance(setup_intent.payment_method, stripe.PaymentMethod) and setup_intent.payment_method.card:
                    fingerprint = setup_intent.payment_method.card.fingerprint
            elif default_payment_method_id and isinstance(default_payment_method_id, str): # Check if it's a subscription event
                payment_method = stripe.PaymentMethod.retrieve(default_payment_method_id)
                if payment_method.card:
                    fingerprint = payment_method.card.fingerprint
            
            # Fallback: check if fingerprint is directly on the event data object
            payment_method_details = event_data_object.get("payment_method_details")
            if not fingerprint and payment_method_details:
                card_details = payment_method_details.get("card", {})
                if card_details and card_details.get("fingerprint"):
                    fingerprint = card_details.get("fingerprint")

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe API error retrieving payment method for fingerprint: {e}",
                event_id=event_id_for_logging,
                payment_intent_id=payment_intent_id,
                setup_intent_id=setup_intent_id,
                default_payment_method_id=default_payment_method_id,
                exc_info=True
            )
        return fingerprint

    async def handle_checkout_session_completed(self, event: stripe.Event):
        """
        Handles the `checkout.session.completed` event.
        - Retrieves PaymentMethod fingerprint.
        - Checks fingerprint against UsedTrialCardFingerprint.
        - If duplicate, rejects trial (logs, potentially updates user status, publishes user.trial.blocked).
        - If unique, proceeds (Stripe will likely create subscription).
        """
        checkout_session = event.data.object
        event_id = event.id
        logger.info(f"Processing checkout.session.completed: {event_id}", event_id=event_id, checkout_session_id=checkout_session.id)

        user_id = checkout_session.get("client_reference_id") or checkout_session.get("metadata", {}).get("user_id")
        stripe_customer_id = checkout_session.get("customer")
        stripe_subscription_id = checkout_session.get("subscription") # May be null if checkout is for a one-time payment

        if not user_id:
            logger.error(f"User ID not found in checkout.session.completed event: {event_id}", event_id=event_id)
            # This is a critical issue, cannot proceed without user context.
            # Return 200 to Stripe to prevent retries for this malformed event data from our side.
            return

        card_fingerprint = await self.get_card_fingerprint_from_event(checkout_session, event_id)

        if not card_fingerprint:
            logger.warning(f"Card fingerprint not found for checkout.session.completed: {event_id}. Cannot perform trial uniqueness check.", event_id=event_id)
            # Depending on policy, this might be an error or a pass-through if trial check is paramount.
            # For now, log and proceed. If a subscription is created, fingerprint check will happen there.
            return

        # Card Uniqueness Gate (FR-4)
        # stmt = select(UsedTrialCardFingerprint).where(UsedTrialCardFingerprint.stripe_card_fingerprint == card_fingerprint)
        # result = await self.db.execute(stmt)
        # existing_fingerprint_use = await result.scalars().first()

        # if existing_fingerprint_use:
        #     logger.warning(
        #         f"Duplicate card fingerprint detected for trial attempt: User ID {user_id}, Fingerprint {card_fingerprint}",
        #         event_id=event_id,
        #         user_id=user_id,
        #         card_fingerprint=card_fingerprint,
        #         existing_use_user_id=existing_fingerprint_use.user_id,
        #         existing_use_subscription_id=existing_fingerprint_use.stripe_subscription_id
        #     )
        #     # If a subscription was created by this checkout, attempt to cancel it immediately.
        #     if stripe_subscription_id:
        #         try:
        #             logger.info(f"Attempting to cancel Stripe subscription {stripe_subscription_id} due to duplicate fingerprint.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
        #             stripe.Subscription.delete(stripe_subscription_id) # Or update(cancel_at_period_end=True) then immediate cancel if preferred
        #             logger.info(f"Successfully canceled Stripe subscription {stripe_subscription_id}.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
        #         except stripe.error.StripeError as e:
        #             logger.error(
        #                 f"Stripe API error canceling subscription {stripe_subscription_id} due to duplicate fingerprint: {e}",
        #                 event_id=event_id,
        #                 stripe_subscription_id=stripe_subscription_id,
        #                 exc_info=True
        #             )
            
        #     # Update user status to 'trial_rejected' or similar
        #     user = await self.db.get(User, user_id)
        #     if user:
        #         user.account_status = "trial_rejected" # Ensure this status is defined in User model/enum
        #         try:
        #             await self.db.commit()
        #             logger.info(f"User {user_id} account_status set to 'trial_rejected'.", user_id=user_id, event_id=event_id)
        #         except SQLAlchemyError as e:
        #             await self.db.rollback()
        #             logger.error(f"DB error updating user {user_id} status to trial_rejected: {e}", user_id=user_id, event_id=event_id, exc_info=True)


        #     # Publish user.trial.blocked event
        #     await self.event_publisher.publish_user_trial_blocked(
        #         user_id=user_id,
        #         stripe_customer_id=stripe_customer_id,
        #         stripe_subscription_id=stripe_subscription_id, # The one that was (attempted to be) created
        #         reason="duplicate_card_fingerprint",
        #         blocked_card_fingerprint=card_fingerprint
        #     )
        #     # logger.info(f"Published user.trial.blocked event for user {user_id}", user_id=user_id, event_id=event_id) # Covered by publisher log

        # else:
        #     logger.info(
        #         f"Card fingerprint {card_fingerprint} is unique for trial. User ID {user_id}.",
        # Card duplication check disabled. Assuming card is unique.
        logger.info(
            f"Card fingerprint {card_fingerprint} processing for trial. User ID {user_id}. Duplication check disabled.",
                event_id=event_id,
                user_id=user_id,
                card_fingerprint=card_fingerprint
            )
            # Fingerprint will be stored by customer.subscription.created if a trial subscription is made.
            # No direct action here other than logging success of this check.

        logger.info(f"Finished processing checkout.session.completed: {event_id}", event_id=event_id)

    async def handle_customer_subscription_created(self, event: stripe.Event):
        """
        Handles the `customer.subscription.created` event.
        - Updates local Subscription record.
        - If trial, performs card fingerprint check and stores fingerprint.
        - If trial & unique card & trial not consumed: grants credits, updates User flags, publishes event.
        """
        subscription_data = event.data.object
        event_id = event.id
        logger.info(f"Processing customer.subscription.created: {event_id}", event_id=event_id, stripe_subscription_id=subscription_data.id)

        stripe_customer_id = subscription_data.customer
        stripe_subscription_id = subscription_data.id
        subscription_status = subscription_data.status
        stripe_price_id = None
        items_data = subscription_data.get("items", {}).get("data")
        if items_data and len(items_data) > 0:
            price_data = items_data[0].get("price")
            if price_data:
                stripe_price_id = price_data.get("id")
        
        trial_end_ts = subscription_data.get("trial_end")
        trial_end_date = datetime.fromtimestamp(trial_end_ts, timezone.utc) if trial_end_ts else None

        # Attempt to get user_id from metadata, or map from stripe_customer_id
        user_id = subscription_data.metadata.get("user_id")
        if not user_id:
            user_stmt = select(User.id).where(User.stripe_customer_id == stripe_customer_id)
            user_result = await self.db.execute(user_stmt)
            user_id = await user_result.scalars().first()
        
        if not user_id:
            logger.error(f"User ID not found for customer.subscription.created: {event_id}, Stripe Customer: {stripe_customer_id}", event_id=event_id, stripe_customer_id=stripe_customer_id)
            return # Cannot proceed without user context

        if subscription_status == 'trialing':
            card_fingerprint = await self.get_card_fingerprint_from_event(subscription_data, event_id)

            if not card_fingerprint:
                logger.error(f"Card fingerprint not found for trialing subscription {stripe_subscription_id}. Critical for trial logic.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                # This is a severe issue. We might need to cancel the trial if we can't verify/store fingerprint.
                # For now, log and alert. Consider raising an exception to let Stripe retry, hoping fingerprint becomes available.
                # However, if it's persistently missing, manual intervention or a different strategy is needed.
                # Let's assume for now we cannot proceed with trial credit grant without fingerprint.
                # To prevent retries on a permanent issue, we might return 200 after logging.
                # For this implementation, let's raise to signal an issue.
                await self.db.rollback()
                raise ValueError(f"Card fingerprint missing for trial subscription {stripe_subscription_id}")

        # Update/Create local Subscription record
        db_subscription = await get_or_create_subscription(self.db, user_id, stripe_subscription_id)
        db_subscription.stripe_customer_id = stripe_customer_id # Ensure this is set/updated
        db_subscription.status = subscription_status
        db_subscription.stripe_price_id = stripe_price_id
        db_subscription.trial_end_date = trial_end_date
        db_subscription.current_period_start = datetime.fromtimestamp(subscription_data.current_period_start, timezone.utc) if subscription_data.current_period_start else None
        db_subscription.current_period_end = datetime.fromtimestamp(subscription_data.current_period_end, timezone.utc) if subscription_data.current_period_end else None
        db_subscription.cancel_at_period_end = subscription_data.cancel_at_period_end
        
        try:
            await self.db.merge(db_subscription) # merge to update if exists, or insert if new via get_or_create
            # await self.db.commit() # Commit later after all operations for this event
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"DB error updating/creating subscription {stripe_subscription_id} for user {user_id}: {e}", event_id=event_id, user_id=user_id, exc_info=True)
            raise

        if subscription_status == 'trialing':

            # Get user to check if they've already consumed their trial
            user = await self.db.get(User, user_id)
            if not user: # Should not happen if user_id was resolved
                logger.error(f"User {user_id} not found when checking trial eligibility.", event_id=event_id, user_id=user_id)
                return
                
            # Only store fingerprint and check for duplicates if user hasn't consumed trial
            if not user.has_consumed_initial_trial:
                # Store Card Fingerprint (FR-4)
                # Get default_payment_method if it exists, otherwise use None
                default_payment_method = getattr(subscription_data, 'default_payment_method', None)
                
                # new_fingerprint_record = UsedTrialCardFingerprint(
                #     user_id=user_id,
                #     stripe_card_fingerprint=card_fingerprint,
                #     stripe_payment_method_id=default_payment_method,
                #     stripe_subscription_id=stripe_subscription_id,
                #     stripe_customer_id=stripe_customer_id
                # )
                # try:
                #     self.db.add(new_fingerprint_record)
                #     await self.db.flush() # Try to flush to catch unique constraint violation early
                #     logger.info(f"Stored unique card fingerprint {card_fingerprint} for trial subscription {stripe_subscription_id}.", event_id=event_id, card_fingerprint=card_fingerprint)
                # except IntegrityError: # uq_trial_card_fingerprint violation
                #     await self.db.rollback()
                #     logger.warning(
                #         f"Duplicate card fingerprint {card_fingerprint} detected during customer.subscription.created for trial. User ID {user_id}.",
                #         event_id=event_id, user_id=user_id, card_fingerprint=card_fingerprint
                #     )
                #     try:
                #         logger.info(f"Attempting to cancel Stripe trial subscription {stripe_subscription_id} due to duplicate fingerprint.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                #         stripe.Subscription.delete(stripe_subscription_id)
                #         logger.info(f"Successfully canceled Stripe trial subscription {stripe_subscription_id}.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                #         db_subscription.status = "canceled" # Update local subscription status
                #         await self.db.merge(db_subscription)
                #     except stripe.error.StripeError as e:
                #         logger.error(f"Stripe API error canceling trial subscription {stripe_subscription_id} due to duplicate fingerprint: {e}", event_id=event_id, exc_info=True)
                
                #     user = await self.db.get(User, user_id)
                #     if user:
                #         user.account_status = "trial_rejected"
                #         await self.db.merge(user)
                    
                #     await self.event_publisher.publish_user_trial_blocked(
                #         user_id=user_id,
                #         stripe_customer_id=stripe_customer_id,
                #         stripe_subscription_id=stripe_subscription_id,
                #         reason="duplicate_card_fingerprint",
                #         blocked_card_fingerprint=card_fingerprint
                #     )
                #     # logger.info(f"Published user.trial.blocked event for user {user_id} due to duplicate fingerprint on subscription creation.", user_id=user_id, event_id=event_id) # Covered by publisher log
                #     await self.db.commit() # Commit changes (user status, subscription status)
                #     return # Stop processing, trial rejected

                # Card duplication check and fingerprint storage disabled.
                logger.info(f"Card fingerprint {card_fingerprint} processing for trial subscription {stripe_subscription_id}. Duplication check and storage disabled.", event_id=event_id, card_fingerprint=card_fingerprint)

                # Grant Initial Credits & Update User (assuming fingerprint was unique as check is disabled)
                # We already have the user object from earlier check
                
                # We only reach this point if user hasn't consumed trial and fingerprint is unique
                # Ensure UserCredit record exists
                user_credit = await self.db.execute(select(UserCredit).where(UserCredit.user_id == user_id))
                user_credit_record = await user_credit.scalars().first()
                if not user_credit_record:
                    user_credit_record = UserCredit(user_id=user_id, balance=0)
                    self.db.add(user_credit_record)
                    await self.db.flush() # Get ID if new

                user_credit_record.balance += settings.FREE_TRIAL_CREDITS
                
                credit_tx = CreditTransaction(
                    user_id=user_id,
                    user_credit_id=user_credit_record.id,
                    transaction_type=TransactionType.TRIAL_CREDIT_GRANT,
                    amount=settings.FREE_TRIAL_CREDITS,
                    reference_id=stripe_subscription_id,
                    description=f"Initial {settings.FREE_TRIAL_CREDITS} free trial credits"
                )
                self.db.add(credit_tx)
                
                user.has_consumed_initial_trial = True
                user.account_status = 'trialing'
                
                await self.event_publisher.publish_user_trial_started(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    trial_end_date=trial_end_date,
                    credits_granted=settings.FREE_TRIAL_CREDITS
                )
                # logger.info(f"Granted 10 trial credits to user {user_id}. Account status 'trialing'. Published user.trial.started.", event_id=event_id, user_id=user_id) # Covered by publisher log
            else:
                # Even if user has already consumed trial, we still set account status to trialing
                user.account_status = "trialing"
                await self.db.merge(user)
                logger.info(f"User {user_id} has already consumed initial trial. No credits granted for subscription {stripe_subscription_id}.", event_id=event_id, user_id=user_id)
        
        try:
            await self.db.commit() # Commit all changes for this event
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"DB commit error for customer.subscription.created {event_id}: {e}", event_id=event_id, exc_info=True)
            raise
            
        logger.info(f"Finished processing customer.subscription.created: {event_id}", event_id=event_id)

    async def handle_customer_subscription_updated(self, event: stripe.Event):
        """
        Handles the `customer.subscription.updated` event.
        - Updates local Subscription record.
        - Updates User.account_status based on Subscription.status changes.
        - Publishes internal events (user.account.frozen, user.account.unfrozen).
        """
        subscription_data = event.data.object
        event_id = event.id
        logger.info(f"Processing customer.subscription.updated: {event_id}", event_id=event_id, stripe_subscription_id=subscription_data.id)

        stripe_customer_id = subscription_data.customer
        stripe_subscription_id = subscription_data.id
        new_stripe_status = subscription_data.status
        
        # Attempt to get user_id from metadata, or map from stripe_customer_id
        user_id = subscription_data.metadata.get("user_id")
        if not user_id:
            user_stmt = select(User.id).where(User.stripe_customer_id == stripe_customer_id)
            user_result = await self.db.execute(user_stmt)
            user_id = await user_result.scalars().first()

        if not user_id:
            logger.error(f"User ID not found for customer.subscription.updated: {event_id}, Stripe Customer: {stripe_customer_id}", event_id=event_id, stripe_customer_id=stripe_customer_id)
            return

        db_subscription = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        subscription_record = await db_subscription.scalars().first()

        if not subscription_record:
            logger.warning(f"Local subscription record not found for stripe_subscription_id {stripe_subscription_id} during update. Creating one.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
            subscription_record = await get_or_create_subscription(self.db, user_id, stripe_subscription_id)
            # Ensure stripe_customer_id is set if it was missing
            if not subscription_record.stripe_customer_id:
                subscription_record.stripe_customer_id = stripe_customer_id


        # Update subscription record fields
        subscription_record.status = new_stripe_status
        new_stripe_price_id = None
        items_data_updated = subscription_data.get("items", {}).get("data")
        if items_data_updated and len(items_data_updated) > 0:
            price_data_updated = items_data_updated[0].get("price")
            if price_data_updated:
                 new_stripe_price_id = price_data_updated.get("id")
        subscription_record.stripe_price_id = new_stripe_price_id if new_stripe_price_id else subscription_record.stripe_price_id
        
        trial_end_ts = subscription_data.get("trial_end")
        # Use getattr for safe access before merge
        subscription_record.trial_end_date = datetime.fromtimestamp(trial_end_ts, timezone.utc) if trial_end_ts else getattr(subscription_record, 'trial_end_date', None)
        
        subscription_record.current_period_start = datetime.fromtimestamp(subscription_data.current_period_start, timezone.utc) if subscription_data.current_period_start else getattr(subscription_record, 'current_period_start', None)
        subscription_record.current_period_end = datetime.fromtimestamp(subscription_data.current_period_end, timezone.utc) if subscription_data.current_period_end else getattr(subscription_record, 'current_period_end', None)
        # cancel_at_period_end is boolean, default should be False if not present
        subscription_record.cancel_at_period_end = subscription_data.cancel_at_period_end if hasattr(subscription_data, 'cancel_at_period_end') else getattr(subscription_record, 'cancel_at_period_end', False)
        
        canceled_at_ts = subscription_data.get("canceled_at")
        subscription_record.canceled_at = datetime.fromtimestamp(canceled_at_ts, timezone.utc) if canceled_at_ts else getattr(subscription_record, 'canceled_at', None)
        
        await self.db.merge(subscription_record)

        # Update User.account_status
        user = await self.db.get(User, user_id)
        if not user:
            logger.error(f"User {user_id} not found when updating account status for subscription {stripe_subscription_id}.", event_id=event_id, user_id=user_id)
            await self.db.rollback()
            return

        previous_account_status = user.account_status
        new_account_status = previous_account_status # Default to no change

        if new_stripe_status == 'active':
            new_account_status = 'active'
        elif new_stripe_status == 'trialing':
            new_account_status = 'trialing'
        elif new_stripe_status in ['past_due', 'incomplete', 'unpaid']: # Stripe uses these for payment issues
            new_account_status = 'frozen'
        elif new_stripe_status == 'canceled':
            new_account_status = 'canceled'
        
        if user.account_status != new_account_status:
            user.account_status = new_account_status
            logger.info(f"User {user_id} account_status changed from {previous_account_status} to {new_account_status} due to subscription {stripe_subscription_id} update.",
                        event_id=event_id, user_id=user_id, previous_status=previous_account_status, new_status=new_account_status)

            # Publish events based on status change
            if new_account_status == 'frozen' and previous_account_status != 'frozen':
                await self.event_publisher.publish_user_account_frozen(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    reason="subscription_status_change" # Or more specific reason if available
                )
                # logger.info(f"Published user.account.frozen event for user {user_id}", user_id=user_id, event_id=event_id) # Covered by publisher log
            elif new_account_status == 'active' and previous_account_status == 'frozen':
                await self.event_publisher.publish_user_account_unfrozen(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    reason="subscription_status_change"
                )
                # logger.info(f"Published user.account.unfrozen event for user {user_id}", user_id=user_id, event_id=event_id) # Covered by publisher log
        
        try:
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"DB commit error for customer.subscription.updated {event_id}: {e}", event_id=event_id, exc_info=True)
            raise

        logger.info(f"Finished processing customer.subscription.updated: {event_id}", event_id=event_id)

    async def handle_invoice_payment_succeeded(self, event: stripe.Event):
        """
        Handles the `invoice.payment_succeeded` event.
        - Updates User.account_status to 'active'.
        - Publishes user.invoice.paid event.
        - If resolves past_due, publishes user.account.unfrozen.
        """
        invoice_data = event.data.object
        event_id = event.id
        logger.info(f"Processing invoice.payment_succeeded: {event_id}", event_id=event_id, stripe_invoice_id=invoice_data.id)

        stripe_customer_id = invoice_data.customer
        stripe_subscription_id = invoice_data.subscription # Can be null for one-off invoices

        user_id = invoice_data.customer_details.get("metadata", {}).get("user_id") # Assuming user_id is in customer metadata
        if not user_id and stripe_customer_id: # Fallback: try to get from our User table
            user_stmt = select(User.id).where(User.stripe_customer_id == stripe_customer_id)
            user_result = await self.db.execute(user_stmt)
            user_id = await user_result.scalars().first()
        
        if not user_id:
            logger.error(f"User ID not found for invoice.payment_succeeded: {event_id}, Stripe Customer: {stripe_customer_id}", event_id=event_id, stripe_customer_id=stripe_customer_id)
            return

        user = await self.db.get(User, user_id)
        if not user:
            logger.error(f"User {user_id} not found for invoice.payment_succeeded: {event_id}", event_id=event_id, user_id=user_id)
            return

        previous_account_status = user.account_status
        
        # If related to a subscription, ensure subscription is marked active
        if stripe_subscription_id:
            db_sub = await self.db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id))
            subscription_record = await db_sub.scalars().first()
            if subscription_record and subscription_record.status != 'active':
                subscription_record.status = 'active' # Or whatever Stripe status is on the sub now
                await self.db.merge(subscription_record)
                logger.info(f"Subscription {stripe_subscription_id} status updated to 'active' due to invoice payment.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)

        # Update user account status to 'active'
        if user.account_status != 'active':
            user.account_status = 'active'
            logger.info(f"User {user_id} account_status changed from {previous_account_status} to 'active' due to invoice payment.",
                        event_id=event_id, user_id=user_id, previous_status=previous_account_status)

            if previous_account_status == 'frozen':
                await self.event_publisher.publish_user_account_unfrozen(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    reason="invoice_paid_after_failure"
                )
                # logger.info(f"Published user.account.unfrozen event for user {user_id}", user_id=user_id, event_id=event_id) # Covered by publisher log
        
        # Publish user.invoice.paid event
        await self.event_publisher.publish_user_invoice_paid(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=invoice_data.id,
            amount_paid=getattr(invoice_data, 'amount_paid', 0), # Default to 0 if not present
            currency=getattr(invoice_data, 'currency', None), # Default to None
            billing_reason=getattr(invoice_data, 'billing_reason', None), # Default to None
            invoice_pdf_url=getattr(invoice_data, 'invoice_pdf', None) # Default to None
        )
        # logger.info(f"Published user.invoice.paid event for user {user_id}, invoice {invoice_data.id}", user_id=user_id, event_id=event_id, stripe_invoice_id=invoice_data.id) # Covered by publisher log

        try:
            await self.db.commit()
        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"DB commit error for invoice.payment_succeeded {event_id}: {e}", event_id=event_id, exc_info=True)
            raise
            
        logger.info(f"Finished processing invoice.payment_succeeded: {event_id}", event_id=event_id)

    async def handle_invoice_payment_failed(self, event: stripe.Event):
        """
        Handles the `invoice.payment_failed` event.
        - Updates User.account_status to 'frozen'.
        - Updates Subscription.status to 'past_due' or equivalent.
        - Publishes user.invoice.failed event.
        - Publishes user.account.frozen event.
        """
        invoice_data = event.data.object
        event_id = event.id
        logger.info(f"Processing invoice.payment_failed: {event_id}", event_id=event_id, stripe_invoice_id=invoice_data.id)

        stripe_customer_id = invoice_data.customer
        stripe_subscription_id = invoice_data.subscription # Can be null

        user_id = invoice_data.customer_details.get("metadata", {}).get("user_id")
        if not user_id and stripe_customer_id:
            user_stmt = select(User.id).where(User.stripe_customer_id == stripe_customer_id)
            user_result = await self.db.execute(user_stmt)
            _scalars_res_user = user_result.scalars() # type: ignore
            user_id = await _scalars_res_user.first()

        if not user_id:
            logger.error(f"User ID not found for invoice.payment_failed: {event_id}, Stripe Customer: {stripe_customer_id}", event_id=event_id, stripe_customer_id=stripe_customer_id)
            return

        user = await self.db.get(User, user_id)
        if not user:
            logger.error(f"User {user_id} not found for invoice.payment_failed: {event_id}", event_id=event_id, user_id=user_id)
            return

        previous_account_status = user.account_status
        needs_commit = False

        # Only freeze account if related to a subscription payment failure
        if stripe_subscription_id and invoice_data.billing_reason in ['subscription_cycle', 'subscription_create', 'subscription_update']:
            db_sub = await self.db.execute(select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id))
            _scalars_res_sub = db_sub.scalars() # type: ignore
            subscription_record = await _scalars_res_sub.first()
            
            if subscription_record:
                # Update subscription status based on Stripe's recommendation or a generic 'past_due'
                # Stripe might automatically set the subscription status, this webhook confirms the invoice failure part.
                # We might just log this or set a specific local status if needed.
                # For now, let's assume Stripe's `customer.subscription.updated` handles the definitive sub status.
                logger.info(f"Invoice payment failed for subscription {stripe_subscription_id}. Relying on subscription.updated for final status.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
            else:
                 logger.warning(f"Subscription record {stripe_subscription_id} not found for failed invoice {invoice_data.id}. Attempting to create/retrieve.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                 subscription_record = await get_or_create_subscription(self.db, user_id, stripe_subscription_id)
                 if subscription_record:
                     if not subscription_record.stripe_customer_id:
                         subscription_record.stripe_customer_id = stripe_customer_id
                     # Set status to past_due or similar, as payment failed
                     subscription_record.status = "past_due" # Or a more specific status from Stripe if available on invoice
                     await self.db.merge(subscription_record)
                     needs_commit = True # Ensure this change is committed
                 else:
                     logger.error(f"Failed to get or create subscription {stripe_subscription_id} for user {user_id} after invoice payment failure.", event_id=event_id, user_id=user_id)
                     # If we still don't have a subscription record, we might not be able to proceed with freezing logic tied to it.
                     # However, the user account itself might still be frozen based on the invoice failure.

            # Freeze the user account status if not already frozen
            if user.account_status != 'frozen':
                user.account_status = 'frozen'
                needs_commit = True
                logger.info(f"User {user_id} account_status changed from {previous_account_status} to 'frozen' due to invoice payment failure.",
                            event_id=event_id, user_id=user_id, previous_status=previous_account_status)
                
                # Publish user.account.frozen event
                await self.event_publisher.publish_user_account_frozen(
                    user_id=user_id,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    reason="invoice_payment_failed"
                )
                # logger.info(f"Published user.account.frozen event for user {user_id}", user_id=user_id, event_id=event_id) # Covered by publisher log
        else:
             logger.info(f"Invoice payment failed {invoice_data.id} not related to a subscription cycle/create/update. No account status change.", event_id=event_id, billing_reason=invoice_data.billing_reason)


        # Publish user.invoice.failed event regardless of account status change
        await self.event_publisher.publish_user_invoice_failed(
            user_id=user_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_invoice_id=invoice_data.id,
            stripe_charge_id=getattr(invoice_data, 'charge', None), # Use getattr for safe access
            failure_reason=getattr(invoice_data.last_payment_error, 'message', None) if hasattr(invoice_data, 'last_payment_error') and invoice_data.last_payment_error else None,
            next_payment_attempt_date=datetime.fromtimestamp(invoice_data.next_payment_attempt, timezone.utc) if hasattr(invoice_data, 'next_payment_attempt') and invoice_data.next_payment_attempt else None
        )
        # logger.info(f"Published user.invoice.failed event for user {user_id}, invoice {invoice_data.id}", user_id=user_id, event_id=event_id, stripe_invoice_id=invoice_data.id) # Covered by publisher log

        if needs_commit:
            try:
                await self.db.commit()
            except SQLAlchemyError as e:
                await self.db.rollback()
                logger.error(f"DB commit error for invoice.payment_failed {event_id}: {e}", event_id=event_id, exc_info=True)
                raise

        logger.info(f"Finished processing invoice.payment_failed: {event_id}", event_id=event_id)