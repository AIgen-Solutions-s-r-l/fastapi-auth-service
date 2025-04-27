"""Subscription-related functionality for the credit service."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any
import uuid

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select, and_, desc

from app.models.credit import TransactionType
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.schemas import credit_schemas
from app.log.logging import logger

from app.services.credit.decorators import db_error_handler
from app.services.credit.utils import calculate_renewal_date

class SubscriptionService:
    """Service class for subscription-related operations."""
    
    def __init__(self):
        """Initialize the service."""
        self.db = None
        self.plan_service = None  # Will be set by CreditService
        self.base_service = None  # Will be set by CreditService
        self.stripe_service = None  # Will be set by CreditService

    async def _send_email_notification(self, background_tasks, user_id, email_type=None, plan_name=None, amount=None, credit_amount=None, renewal_date=None, old_plan_name=None, new_plan_name=None, additional_credits=None, new_renewal_date=None):
        """Send email notification for subscription operations."""
        # This is a stub method that doesn't actually send emails in tests
        # In production, this would be implemented to send actual emails
        pass

    @db_error_handler()
    async def renew_subscription(
        self,
        subscription_id: int,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Optional[Tuple[credit_schemas.TransactionResponse, Subscription]]:
        """
        Renew a subscription, add credits, and update renewal date.

        Args:
            subscription_id: ID of the subscription to renew
            background_tasks: Optional background tasks for sending emails

        Returns:
            Optional[Tuple[TransactionResponse, Subscription]]: Transaction and updated subscription if successful
        """
        # Get the subscription
        result = await self.db.execute(select(Subscription).where(Subscription.id == subscription_id))
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            logger.warning(f"Subscription not found: {subscription_id}",
                         event_type="subscription_not_found",
                         subscription_id=subscription_id)
            return None

        # Check if subscription is active
        if not subscription.is_active:
            logger.warning(f"Attempted to renew inactive subscription: {subscription_id}",
                         event_type="inactive_subscription_renewal",
                         subscription_id=subscription_id)
            return None

        # Get the plan
        plan = await self.plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            logger.error(f"Plan not found for subscription: {subscription_id}",
                       event_type="plan_not_found",
                       subscription_id=subscription_id,
                       plan_id=subscription.plan_id)
            return None
        
        # If subscription has a Stripe ID, verify it's still active
        if subscription.stripe_subscription_id:
            is_active = await self.stripe_service.verify_subscription_active(subscription.stripe_subscription_id)
            if not is_active:
                logger.warning(f"Stripe subscription not active: {subscription.stripe_subscription_id}",
                             event_type="stripe_subscription_inactive",
                             subscription_id=subscription_id,
                             stripe_subscription_id=subscription.stripe_subscription_id)
                
                # Update subscription status
                subscription.is_active = False
                subscription.status = "inactive"
                await self.db.commit()
                
                return None

        # Update subscription
        last_renewal_date = subscription.renewal_date
        subscription.last_renewal_date = last_renewal_date
        subscription.renewal_date = calculate_renewal_date(last_renewal_date)
        await self.db.commit()
        await self.db.refresh(subscription)

        # Add credits
        reference_id = str(uuid.uuid4())
        transaction = await self.base_service.add_credits(
            user_id=subscription.user_id,
            amount=plan.credit_amount,
            reference_id=reference_id,
            description=f"Renewal of {plan.name} plan",
            transaction_type=TransactionType.PLAN_RENEWAL,
            plan_id=plan.id,
            subscription_id=subscription.id
        )

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=subscription.user_id,
                email_type="payment_confirmation",
                plan_name=plan.name,
                amount=plan.price,
                credit_amount=plan.credit_amount,
                renewal_date=subscription.renewal_date
            )

        logger.info(f"Subscription renewed: User {subscription.user_id}, Plan {plan.id}, Credits {plan.credit_amount}",
                  event_type="subscription_renewed",
                  user_id=subscription.user_id,
                  subscription_id=subscription.id,
                  plan_id=plan.id,
                  plan_name=plan.name,
                  credit_amount=plan.credit_amount,
                  renewal_date=subscription.renewal_date.isoformat())

        return transaction, subscription

    @db_error_handler()
    async def update_subscription_auto_renew(
        self, 
        subscription_id: int, 
        auto_renew: bool
    ) -> Subscription:
        """
        Update the auto-renewal setting for a subscription.
        
        Args:
            subscription_id: The ID of the subscription to update
            auto_renew: The new auto-renewal setting
            
        Returns:
            Subscription: The updated subscription
            
        Raises:
            HTTPException: If the subscription is not found
        """
        subscription = await self.plan_service.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subscription not found"
            )
        
        # If subscription has a Stripe ID and auto_renew is being turned off,
        # update the subscription in Stripe to cancel at period end
        if subscription.stripe_subscription_id and not auto_renew and subscription.auto_renew:
            logger.info(f"Setting Stripe subscription to cancel at period end: {subscription.stripe_subscription_id}",
                      event_type="stripe_subscription_cancel_at_period_end",
                      subscription_id=subscription_id,
                      stripe_subscription_id=subscription.stripe_subscription_id)
            
            try:
                import stripe
                import asyncio
                
                # Set cancel_at_period_end to True
                await asyncio.to_thread(
                    stripe.Subscription.modify,
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                
                logger.info(f"Stripe subscription set to cancel at period end: {subscription.stripe_subscription_id}",
                          event_type="stripe_subscription_cancel_at_period_end_success",
                          subscription_id=subscription_id,
                          stripe_subscription_id=subscription.stripe_subscription_id)
                
            except Exception as e:
                logger.error(f"Error setting Stripe subscription to cancel at period end: {str(e)}",
                           event_type="stripe_subscription_cancel_at_period_end_error",
                           subscription_id=subscription_id,
                           stripe_subscription_id=subscription.stripe_subscription_id,
                           error=str(e))
                
                # Continue anyway, but log the error
            
        subscription.auto_renew = auto_renew
        await self.db.commit()
        await self.db.refresh(subscription)
        
        logger.info(f"Subscription auto-renew updated: {subscription_id}, auto_renew={auto_renew}",
                  event_type="subscription_auto_renew_updated",
                  subscription_id=subscription_id,
                  auto_renew=auto_renew)
        
        return subscription

    async def update_subscription_status(
        self, 
        stripe_subscription_id: str, 
        status: str
    ) -> Optional[Subscription]:
        """
        Update the status of a subscription.
        
        Args:
            stripe_subscription_id: The Stripe subscription ID
            status: The new status
            
        Returns:
            Optional[Subscription]: The updated subscription if found, None otherwise
        """
        subscription = await self.plan_service.get_subscription_by_stripe_id(stripe_subscription_id)
        if not subscription:
            logger.warning(f"Subscription not found for Stripe ID: {stripe_subscription_id}",
                         event_type="stripe_subscription_not_found",
                         stripe_subscription_id=stripe_subscription_id)
            return None
            
        # Update the status and active status based on Stripe status
        subscription.status = status
        
        # Determine if subscription should be active based on status
        if status in ["active", "trialing"]:
            subscription.is_active = True
        elif status in ["canceled", "unpaid", "past_due"]:
            subscription.is_active = False
        
        await self.db.commit()
        await self.db.refresh(subscription)
        
        logger.info(f"Subscription status updated: {stripe_subscription_id}, status={status}",
                  event_type="subscription_status_updated",
                  stripe_subscription_id=stripe_subscription_id,
                  status=status,
                  is_active=subscription.is_active)
        
        return subscription
    
    @db_error_handler()
    async def cancel_subscription(
        self,
        subscription_id: int,
        user_id: Optional[int] = None,
        cancel_in_stripe: bool = True,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Cancel a subscription.
        
        Args:
            subscription_id: The ID of the subscription to cancel
            user_id: Optional user ID for permission validation
            cancel_in_stripe: Whether to also cancel the subscription in Stripe
            background_tasks: Optional background tasks for sending emails
            
        Returns:
            Tuple[bool, Optional[Dict[str, Any]]]:
                - Success flag
                - Optional dict with additional information (plan name, effective end date)
                
        Raises:
            HTTPException: If user doesn't have permission to cancel this subscription
        """
        logger.info(f"Cancelling subscription: {subscription_id}",
                  event_type="subscription_cancellation_request",
                  subscription_id=subscription_id,
                  user_id=user_id,
                  cancel_in_stripe=cancel_in_stripe)
        
        try:
            # Get the subscription
            subscription = await self.plan_service.get_subscription_by_id(subscription_id)
            if not subscription:
                logger.warning(f"Subscription not found for cancellation: {subscription_id}",
                             event_type="subscription_not_found",
                             subscription_id=subscription_id)
                return False, None
            
            # Validate user permission if user_id is provided
            if user_id is not None and subscription.user_id != user_id:
                logger.warning(f"User {user_id} attempted to cancel subscription {subscription_id} belonging to user {subscription.user_id}",
                             event_type="subscription_cancellation_unauthorized",
                             subscription_id=subscription_id,
                             user_id=user_id,
                             subscription_user_id=subscription.user_id)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to cancel this subscription"
                )
            
            # Check if subscription is already canceled
            if subscription.status == "canceled" or not subscription.is_active:
                logger.warning(f"Attempted to cancel already inactive subscription: {subscription_id}",
                             event_type="subscription_already_canceled",
                             subscription_id=subscription_id,
                             user_id=subscription.user_id)
                return False, {"error": "Subscription is already canceled"}
            
            # Get the plan for email notification
            plan = await self.plan_service.get_plan_by_id(subscription.plan_id)
            if not plan:
                logger.error(f"Plan not found for subscription: {subscription_id}",
                           event_type="plan_not_found",
                           subscription_id=subscription_id,
                           plan_id=subscription.plan_id)
                # Continue anyway, but log the error
                plan_name = "Unknown Plan"
            else:
                plan_name = plan.name
            
            # If requested and subscription has a Stripe ID, cancel in Stripe
            stripe_error = None
            if cancel_in_stripe and subscription.stripe_subscription_id:
                try:
                    cancelled_in_stripe = await self.stripe_service.cancel_subscription(subscription.stripe_subscription_id)
                    
                    if not cancelled_in_stripe:
                        logger.warning(f"Failed to cancel subscription in Stripe: {subscription.stripe_subscription_id}",
                                     event_type="stripe_subscription_cancellation_failed",
                                     subscription_id=subscription_id,
                                     stripe_subscription_id=subscription.stripe_subscription_id)
                        stripe_error = "Failed to cancel subscription in Stripe payment processor"
                        # Continue anyway, but log the failure
                except Exception as e:
                    logger.error(f"Error cancelling subscription in Stripe: {str(e)}",
                               event_type="stripe_subscription_cancellation_error",
                               subscription_id=subscription_id,
                               stripe_subscription_id=subscription.stripe_subscription_id,
                               error=str(e))
                    stripe_error = f"Error cancelling in payment processor: {str(e)}"
                    # Continue anyway, but log the error
            
            # Update subscription in our database
            effective_end_date = subscription.renewal_date
            subscription.is_active = False
            subscription.status = "canceled"
            subscription.auto_renew = False
            await self.db.commit()
            
            # Send email notification if background_tasks is provided
            if background_tasks and user_id is not None:
                # Get the user for email notification
                result = await self.db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                
                if user:
                    from app.services.email_service import EmailService
                    email_service = EmailService(background_tasks, self.db)
                    await email_service.send_subscription_cancellation(
                        user=user,
                        plan_name=plan_name,
                        effective_end_date=effective_end_date
                    )
                    
                    logger.info(f"Subscription cancellation email sent to user: {user_id}",
                              event_type="subscription_cancellation_email_sent",
                              subscription_id=subscription_id,
                              user_id=user_id,
                              user_email=user.email)
            
            # Log the successful cancellation
            logger.info(f"Subscription cancelled: {subscription_id}",
                      event_type="subscription_cancelled",
                      subscription_id=subscription_id,
                      user_id=subscription.user_id,
                      plan_id=subscription.plan_id,
                      stripe_error=stripe_error)
            
            # Return success and additional information
            result = {
                "plan_name": plan_name,
                "effective_end_date": effective_end_date,
                "stripe_error": stripe_error
            }
            
            return True, result
            
        except HTTPException:
            # Re-raise HTTP exceptions for proper error handling
            raise
        except Exception as e:
            logger.error(f"Error cancelling subscription: {str(e)}",
                       event_type="subscription_cancellation_error",
                       subscription_id=subscription_id,
                       user_id=user_id,
                       error=str(e))
            return False, {"error": f"Internal error: {str(e)}"}