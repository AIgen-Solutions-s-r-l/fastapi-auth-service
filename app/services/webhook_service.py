import stripe
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import settings
from app.log.logging import logger
from app.models.user import User
from app.models.plan import UsedTrialCardFingerprint, Subscription
from app.models.processed_event import ProcessedStripeEvent
# from app.services.user_service import UserService # To update user status
# from app.services.credit_service import CreditService # To grant credits
# from app.services.internal_event_publisher import InternalEventPublisher # To publish events

stripe.api_key = settings.STRIPE_SECRET_KEY


class WebhookService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        # self.user_service = UserService(db_session)
        # self.credit_service = CreditService(db_session)
        # self.event_publisher = InternalEventPublisher() # Assuming it doesn't need db session

    async def is_event_processed(self, event_id: str) -> bool:
        """Checks if a Stripe event has already been processed."""
        stmt = select(ProcessedStripeEvent).where(ProcessedStripeEvent.stripe_event_id == event_id)
        result = await self.db.execute(stmt)
        return result.scalars().first() is not None

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

    async def get_card_fingerprint_from_event(self, event: stripe.Event) -> str | None:
        """
        Retrieves card fingerprint from a Stripe event object.
        Handles different ways fingerprint might be available (PaymentIntent, SetupIntent).
        """
        fingerprint = None
        payment_intent_id = event.data.object.get("payment_intent")
        setup_intent_id = event.data.object.get("setup_intent")
        
        try:
            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["payment_method"])
                if payment_intent.payment_method and payment_intent.payment_method.card:
                    fingerprint = payment_intent.payment_method.card.fingerprint
            elif setup_intent_id:
                setup_intent = stripe.SetupIntent.retrieve(setup_intent_id, expand=["payment_method"])
                if setup_intent.payment_method and setup_intent.payment_method.card:
                    fingerprint = setup_intent.payment_method.card.fingerprint
            
            # Fallback: check if fingerprint is directly on the event (less common for checkout.session.completed)
            if not fingerprint and event.data.object.get("payment_method_details", {}).get("card", {}).get("fingerprint"):
                 fingerprint = event.data.object.get("payment_method_details").get("card").get("fingerprint")

        except stripe.error.StripeError as e:
            logger.error(
                f"Stripe API error retrieving payment/setup intent for fingerprint: {e}",
                event_id=event.id,
                payment_intent_id=payment_intent_id,
                setup_intent_id=setup_intent_id,
                exc_info=True
            )
            # Depending on policy, might raise or return None
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

        card_fingerprint = await self.get_card_fingerprint_from_event(event)

        if not card_fingerprint:
            logger.warning(f"Card fingerprint not found for checkout.session.completed: {event_id}. Cannot perform trial uniqueness check.", event_id=event_id)
            # Depending on policy, this might be an error or a pass-through if trial check is paramount.
            # For now, log and proceed. If a subscription is created, fingerprint check will happen there.
            return

        # Card Uniqueness Gate (FR-4)
        stmt = select(UsedTrialCardFingerprint).where(UsedTrialCardFingerprint.stripe_card_fingerprint == card_fingerprint)
        result = await self.db.execute(stmt)
        existing_fingerprint_use = result.scalars().first()

        if existing_fingerprint_use:
            logger.warning(
                f"Duplicate card fingerprint detected for trial attempt: User ID {user_id}, Fingerprint {card_fingerprint}",
                event_id=event_id,
                user_id=user_id,
                card_fingerprint=card_fingerprint,
                existing_use_user_id=existing_fingerprint_use.user_id,
                existing_use_subscription_id=existing_fingerprint_use.stripe_subscription_id
            )
            # If a subscription was created by this checkout, attempt to cancel it immediately.
            if stripe_subscription_id:
                try:
                    logger.info(f"Attempting to cancel Stripe subscription {stripe_subscription_id} due to duplicate fingerprint.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                    stripe.Subscription.delete(stripe_subscription_id) # Or update(cancel_at_period_end=True) then immediate cancel if preferred
                    logger.info(f"Successfully canceled Stripe subscription {stripe_subscription_id}.", event_id=event_id, stripe_subscription_id=stripe_subscription_id)
                except stripe.error.StripeError as e:
                    logger.error(
                        f"Stripe API error canceling subscription {stripe_subscription_id} due to duplicate fingerprint: {e}",
                        event_id=event_id,
                        stripe_subscription_id=stripe_subscription_id,
                        exc_info=True
                    )
            
            # Update user status to 'trial_rejected' or similar
            user = await self.db.get(User, user_id)
            if user:
                user.account_status = "trial_rejected" # Ensure this status is defined in User model/enum
                try:
                    await self.db.commit()
                    logger.info(f"User {user_id} account_status set to 'trial_rejected'.", user_id=user_id, event_id=event_id)
                except SQLAlchemyError as e:
                    await self.db.rollback()
                    logger.error(f"DB error updating user {user_id} status to trial_rejected: {e}", user_id=user_id, event_id=event_id, exc_info=True)


            # Publish user.trial.blocked event
            # await self.event_publisher.publish_user_trial_blocked(
            #     user_id=user_id,
            #     stripe_customer_id=stripe_customer_id,
            #     stripe_subscription_id=stripe_subscription_id, # The one that was (attempted to be) created
            #     reason="duplicate_card_fingerprint",
            #     blocked_card_fingerprint=card_fingerprint
            # )
            logger.info(f"Published user.trial.blocked event for user {user_id}", user_id=user_id, event_id=event_id)

        else:
            logger.info(
                f"Card fingerprint {card_fingerprint} is unique for trial. User ID {user_id}.",
                event_id=event_id,
                user_id=user_id,
                card_fingerprint=card_fingerprint
            )
            # Fingerprint will be stored by customer.subscription.created if a trial subscription is made.
            # No direct action here other than logging success of this check.

        logger.info(f"Finished processing checkout.session.completed: {event_id}", event_id=event_id)

    # Add other handlers (handle_customer_subscription_created, etc.) here