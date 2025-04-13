"""Stripe integration functionality for the credit service."""

from typing import Optional, Dict, Any, List
from datetime import datetime, UTC
from decimal import Decimal
import asyncio

from sqlalchemy import select
from app.models.user import User
from app.models.plan import Subscription
from app.core.config import settings
from app.log.logging import logger
import stripe


class StripeIntegrationService:
    """Service class for Stripe integration operations."""
    
    def __init__(self):
        """Initialize the service."""
        self.db = None
        # Configure Stripe API key
        if settings.STRIPE_SECRET_KEY:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            stripe.api_version = settings.STRIPE_API_VERSION
        else:
            logger.warning("Stripe API key not configured", event_type="stripe_config_warning")

    async def get_user_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[User]:
        """
        Get user by Stripe customer ID.
        
        Args:
            stripe_customer_id: The Stripe customer ID
            
        Returns:
            Optional[User]: The user if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.stripe_customer_id == stripe_customer_id)
        )
        return result.scalar_one_or_none()
    
    async def verify_transaction_id(self, transaction_id: str) -> Dict[str, Any]:
        """
        Verify a transaction ID exists in Stripe and return its details.
        
        Args:
            transaction_id: The Stripe transaction ID to verify
            
        Returns:
            Dict[str, Any]: Transaction details if found, empty dict if not found
            
        Raises:
            Exception: If there's an error communicating with Stripe
        """
        logger.info(f"Verifying Stripe transaction ID: {transaction_id}", 
                  event_type="stripe_transaction_verification",
                  transaction_id=transaction_id)
        
        try:
            payment_intent_verified = False
            subscription_verified = False
            
            # Try to find as PaymentIntent (one-time purchases)
            try:
                payment_intent = await asyncio.to_thread(
                    stripe.PaymentIntent.retrieve,
                    transaction_id
                )
                
                if payment_intent:
                    logger.info(f"Transaction verified as PaymentIntent: {transaction_id}",
                              event_type="stripe_transaction_verified",
                              transaction_id=transaction_id,
                              transaction_type="payment_intent",
                              status=payment_intent.status)
                    
                    # Check if payment is successful
                    if payment_intent.status not in ['succeeded', 'processing']:
                        logger.warning(f"PaymentIntent not in valid state: {payment_intent.status}",
                                     event_type="stripe_transaction_invalid_state",
                                     transaction_id=transaction_id,
                                     status=payment_intent.status)
                    else:
                        payment_intent_verified = True
                        return {
                            "verified": True,
                            "id": payment_intent.id,
                            "object_type": "payment_intent",
                            "amount": Decimal(payment_intent.amount) / 100,  # Convert cents to dollars
                            "customer_id": payment_intent.get('customer'),
                            "status": payment_intent.status
                        }
            except Exception as e:
                logger.debug(f"Not a payment intent: {str(e)}",
                           event_type="stripe_verification_debug",
                           transaction_id=transaction_id,
                           error=str(e))
            
            # Try to find as Subscription
            try:
                subscription = await asyncio.to_thread(
                    stripe.Subscription.retrieve,
                    transaction_id
                )
                
                if subscription:
                    logger.info(f"Transaction verified as Subscription: {transaction_id}",
                              event_type="stripe_transaction_verified",
                              transaction_id=transaction_id,
                              transaction_type="subscription",
                              status=subscription.status)
                    
                    # Check if subscription is active
                    if subscription.status not in ['active', 'trialing']:
                        logger.warning(f"Subscription not in active state: {subscription.status}",
                                     event_type="stripe_transaction_invalid_state",
                                     transaction_id=transaction_id,
                                     status=subscription.status)
                    else:
                        subscription_verified = True
                        # Calculate amount from subscription items
                        amount = Decimal('0.00')
                        plan_id = None
                        if subscription.items.data:
                            item = subscription.items.data[0]
                            if item.plan:
                                amount = Decimal(item.plan.amount) / 100
                                plan_id = item.plan.id
                        
                        return {
                            "verified": True,
                            "id": subscription.id,
                            "object_type": "subscription",
                            "amount": amount,
                            "customer_id": subscription.customer,
                            "status": subscription.status,
                            "plan_id": plan_id,
                            "current_period_end": datetime.fromtimestamp(subscription.current_period_end, UTC)
                        }
            except Exception as e:
                logger.debug(f"Not a subscription: {str(e)}",
                           event_type="stripe_verification_debug",
                           transaction_id=transaction_id,
                           error=str(e))
            
            # Only reach here if both verification attempts failed
            logger.warning(f"Transaction ID not verified: {transaction_id}",
                         event_type="stripe_transaction_not_verified",
                         transaction_id=transaction_id)
            return {"verified": False, "reason": "Transaction not found or not in a valid state"}
            
        except Exception as e:
            logger.error(f"Error verifying transaction: {str(e)}", 
                       event_type="stripe_verification_error",
                       transaction_id=transaction_id,
                       error=str(e))
            raise Exception(f"Error verifying transaction: {str(e)}")
    
    async def check_active_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Check if a user has an active subscription in Stripe.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            Optional[Dict[str, Any]]: Subscription details if found, None otherwise
        """
        logger.info(f"Checking active subscription for user: {user_id}", 
                  event_type="stripe_subscription_check",
                  user_id=user_id)
        
        try:
            # Get user's active subscription from our database
            result = await self.db.execute(
                select(Subscription).where(
                    (Subscription.user_id == user_id) & 
                    (Subscription.is_active == True)  # noqa: E712
                )
            )
            subscription = result.scalar_one_or_none()
            
            if not subscription or not subscription.stripe_subscription_id:
                logger.info(f"No active subscription found for user: {user_id}", 
                          event_type="stripe_subscription_not_found",
                          user_id=user_id)
                return None
            
            # Verify subscription in Stripe
            try:
                stripe_subscription = await asyncio.to_thread(
                    stripe.Subscription.retrieve,
                    subscription.stripe_subscription_id
                )
                
                if not stripe_subscription:
                    logger.warning(f"Stripe subscription not found: {subscription.stripe_subscription_id}", 
                                 event_type="stripe_subscription_not_found",
                                 user_id=user_id,
                                 subscription_id=subscription.id,
                                 stripe_subscription_id=subscription.stripe_subscription_id)
                    return None
                
                # Check if subscription is active in Stripe
                if stripe_subscription.status not in ['active', 'trialing']:
                    logger.warning(f"Stripe subscription not active: {subscription.stripe_subscription_id}", 
                                 event_type="stripe_subscription_inactive",
                                 user_id=user_id,
                                 subscription_id=subscription.id,
                                 stripe_subscription_id=subscription.stripe_subscription_id,
                                 status=stripe_subscription.status)
                    
                    # Update our subscription status
                    subscription.is_active = False
                    subscription.status = stripe_subscription.status
                    await self.db.commit()
                    
                    return None
                
                logger.info(f"Active subscription found for user: {user_id}", 
                          event_type="stripe_subscription_found",
                          user_id=user_id,
                          subscription_id=subscription.id,
                          stripe_subscription_id=subscription.stripe_subscription_id,
                          status=stripe_subscription.status)
                
                # Calculate amount from subscription items
                amount = Decimal('0.00')
                plan_id = None
                if stripe_subscription.items.data:
                    item = stripe_subscription.items.data[0]
                    if item.plan:
                        amount = Decimal(item.plan.amount) / 100
                        plan_id = item.plan.id
                
                return {
                    "subscription_id": subscription.id,
                    "stripe_subscription_id": subscription.stripe_subscription_id,
                    "plan_id": subscription.plan_id,
                    "stripe_plan_id": plan_id,
                    "status": stripe_subscription.status,
                    "amount": amount,
                    "current_period_end": datetime.fromtimestamp(stripe_subscription.current_period_end, UTC)
                }
                
            except Exception as e:
                logger.error(f"Error retrieving Stripe subscription: {str(e)}", 
                           event_type="stripe_subscription_error",
                           user_id=user_id,
                           subscription_id=subscription.id,
                           stripe_subscription_id=subscription.stripe_subscription_id,
                           error=str(e))
                return None
            
        except Exception as e:
            logger.error(f"Error checking active subscription: {str(e)}", 
                       event_type="stripe_subscription_check_error",
                       user_id=user_id,
                       error=str(e))
            return None
    
    async def cancel_subscription(self, stripe_subscription_id: str) -> bool:
        """
        Cancel a subscription in Stripe.
        
        Args:
            stripe_subscription_id: The Stripe subscription ID to cancel
            
        Returns:
            bool: True if cancellation was successful, False otherwise
        """
        logger.info(f"Cancelling Stripe subscription: {stripe_subscription_id}", 
                  event_type="stripe_subscription_cancellation",
                  stripe_subscription_id=stripe_subscription_id)
        
        try:
            # Cancel the subscription immediately
            result = await asyncio.to_thread(
                stripe.Subscription.delete,
                stripe_subscription_id
            )
            
            if result and result.get("status") == "canceled":
                logger.info(f"Stripe subscription cancelled: {stripe_subscription_id}", 
                          event_type="stripe_subscription_cancelled",
                          stripe_subscription_id=stripe_subscription_id)
                return True
            
            logger.warning(f"Failed to cancel Stripe subscription: {stripe_subscription_id}", 
                         event_type="stripe_subscription_cancellation_failed",
                         stripe_subscription_id=stripe_subscription_id,
                         result=result)
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling Stripe subscription: {str(e)}", 
                       event_type="stripe_subscription_cancellation_error",
                       stripe_subscription_id=stripe_subscription_id,
                       error=str(e))
            return False
    
    async def verify_subscription_active(self, stripe_subscription_id: str) -> bool:
        """
        Verify a subscription is active in Stripe.
        
        Args:
            stripe_subscription_id: The Stripe subscription ID to verify
            
        Returns:
            bool: True if subscription is active, False otherwise
        """
        logger.info(f"Verifying Stripe subscription: {stripe_subscription_id}", 
                  event_type="stripe_subscription_verification",
                  stripe_subscription_id=stripe_subscription_id)
        
        try:
            subscription = await asyncio.to_thread(
                stripe.Subscription.retrieve,
                stripe_subscription_id
            )
            
            if not subscription:
                logger.warning(f"Stripe subscription not found: {stripe_subscription_id}", 
                             event_type="stripe_subscription_not_found",
                             stripe_subscription_id=stripe_subscription_id)
                return False
            
            is_active = subscription.status in ['active', 'trialing']
            
            logger.info(f"Stripe subscription verification result: {is_active}", 
                      event_type="stripe_subscription_verification_result",
                      stripe_subscription_id=stripe_subscription_id,
                      status=subscription.status,
                      is_active=is_active)
            
            return is_active
            
        except Exception as e:
            logger.error(f"Error verifying Stripe subscription: {str(e)}", 
                       event_type="stripe_subscription_verification_error",
                       stripe_subscription_id=stripe_subscription_id,
                       error=str(e))
            return False