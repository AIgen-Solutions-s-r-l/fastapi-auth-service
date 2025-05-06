"""Service layer for handling Stripe-related operations."""

import stripe
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone

from app.core.config import settings
from app.models.user import User, Subscription # Assuming Subscription model exists and is related to User
from app.models.plan import Plan # Assuming Plan model exists
from app.log.logging import logger
from app.core.db_exceptions import DatabaseError, NotFoundError

# Initialize Stripe API key
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


class StripeService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def _get_user_active_subscription_from_db(self, user_id: str) -> Subscription:
        """
        Retrieves the user's active or trialing subscription from the database.
        Raises NotFoundError if no such subscription exists.
        """
        logger.debug(f"Fetching active/trialing subscription for user_id: {user_id}")
        
        # Assuming a Subscription model linked to User and Plan
        # and it has a 'stripe_subscription_id' and 'status' (e.g., 'active', 'trialing', 'canceled')
        stmt = (
            select(Subscription)
            .join(User, Subscription.user_id == User.id)
            .where(User.id == user_id)
            .where(Subscription.status.in_(['active', 'trialing'])) # Check for active or trialing
        )
        result = await self.db.execute(stmt)
        subscription = result.scalars().first()

        if not subscription:
            logger.warning(
                "No active or trialing subscription found for user",
                event_type="active_subscription_not_found_db",
                user_id=user_id
            )
            raise NotFoundError("User does not have an active or trialing subscription.")
        
        if not subscription.stripe_subscription_id:
            logger.error(
                "Active/trialing subscription found in DB but missing stripe_subscription_id",
                event_type="subscription_missing_stripe_id",
                user_id=user_id,
                db_subscription_id=subscription.id
            )
            raise DatabaseError("Subscription record is missing Stripe ID.")

        logger.info(
            "Active/trialing subscription found in DB",
            event_type="active_subscription_found_db",
            user_id=user_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            current_db_status=subscription.status
        )
        return subscription

    async def cancel_user_subscription(self, user_id: str, reason: Optional[str] = None) -> dict:
        """
        Cancels a user's Stripe subscription by setting cancel_at_period_end=True.
        Updates the local subscription record status.

        Args:
            user_id: The ID of the user whose subscription is to be canceled.
            reason: Optional reason for cancellation.

        Returns:
            A dictionary with cancellation details:
            {
                "stripe_subscription_id": "sub_...",
                "subscription_status": "active", // Stripe status after update
                "period_end_date": "YYYY-MM-DDTHH:MM:SSZ" // ISO 8601
            }
        
        Raises:
            HTTPException: 
                - 404 if no active subscription is found.
                - 400 if subscription is already canceled or cannot be canceled.
                - 500 for Stripe API errors or other unexpected issues.
        """
        try:
            db_subscription = await self._get_user_active_subscription_from_db(user_id)
        except NotFoundError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found to cancel.")
        except DatabaseError as e:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")


        stripe_subscription_id = db_subscription.stripe_subscription_id

        try:
            logger.info(
                "Attempting to fetch Stripe subscription for cancellation check",
                event_type="stripe_subscription_fetch_for_cancel",
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id
            )
            stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)

            if stripe_sub.status == 'canceled':
                logger.warning(
                    "Subscription is already canceled on Stripe",
                    event_type="subscription_already_canceled_stripe",
                    user_id=user_id,
                    stripe_subscription_id=stripe_subscription_id
                )
                # Update local DB if it's not already marked as canceled
                if db_subscription.status != 'canceled':
                    db_subscription.status = 'canceled'
                    db_subscription.updated_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    await self.db.refresh(db_subscription)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription is already canceled.")

            if stripe_sub.cancel_at_period_end:
                logger.warning(
                    "Subscription is already set to cancel at period end on Stripe",
                    event_type="subscription_already_set_to_cancel_stripe",
                    user_id=user_id,
                    stripe_subscription_id=stripe_subscription_id
                )
                # Optionally update local DB status if needed, e.g., to 'pending_cancellation'
                # For now, we'll just inform the user.
                period_end_dt = datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
                return {
                    "stripe_subscription_id": stripe_sub.id,
                    "subscription_status": stripe_sub.status, # Should be 'active'
                    "period_end_date": period_end_dt.isoformat()
                }
                # Or raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription is already set to cancel at period end.")


            logger.info(
                "Attempting to update Stripe subscription to cancel_at_period_end=True",
                event_type="stripe_subscription_cancel_update",
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id
            )
            updated_stripe_sub = stripe.Subscription.update(
                stripe_subscription_id,
                cancel_at_period_end=True,
                # You could pass the cancellation reason to Stripe metadata if desired
                # metadata={'cancellation_reason': reason} if reason else None
            )
            logger.info(
                "Stripe subscription successfully updated to cancel_at_period_end=True",
                event_type="stripe_subscription_cancel_success",
                user_id=user_id,
                stripe_subscription_id=updated_stripe_sub.id,
                new_stripe_status=updated_stripe_sub.status
            )

            # Update local database subscription record
            # The status might remain 'active' locally until a webhook confirms 'canceled'
            # or you might introduce a 'pending_cancellation' status.
            # For now, let's assume the webhook `customer.subscription.updated` will handle final status.
            # We can log the intent here.
            db_subscription.updated_at = datetime.now(timezone.utc)
            # db_subscription.status = 'pending_cancellation' # Example if you have such a status
            # Or simply note that it's set to cancel:
            # db_subscription.cancel_at_period_end_flag = True # If you add such a field
            
            await self.db.commit()
            await self.db.refresh(db_subscription)

            period_end_dt = datetime.fromtimestamp(updated_stripe_sub.current_period_end, tz=timezone.utc)

            return {
                "stripe_subscription_id": updated_stripe_sub.id,
                "subscription_status": updated_stripe_sub.status, # This will likely still be 'active'
                "period_end_date": period_end_dt.isoformat()
            }

        except stripe.error.StripeError as e:
            logger.error(
                "Stripe API error during subscription cancellation",
                event_type="stripe_api_error_cancel",
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id,
                error_message=str(e),
                stripe_error_type=e.code 
            )
            # More specific error handling based on e.code if needed
            if e.code == 'resource_missing':
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found on Stripe.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stripe API error: {str(e)}")
        except Exception as e:
            logger.error(
                "Unexpected error during subscription cancellation process",
                event_type="subscription_cancel_service_unexpected_error",
                user_id=user_id,
                stripe_subscription_id=stripe_subscription_id,
                error_type=type(e).__name__,
                error_details=str(e)
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")