"""Credit service module for managing user credits and subscriptions."""

from app.services.credit.base import BaseCreditService
from app.services.credit.plan import PlanService
from app.services.credit.transaction import TransactionService
from app.services.credit.subscription import SubscriptionService
from app.services.credit.stripe_integration import StripeIntegrationService
from app.services.credit.exceptions import InsufficientCreditsError
from app.log.logging import logger


class CreditService:
    """
    Comprehensive service for managing user credits, plans, and subscriptions.
    
    This service uses composition to combine functionality from multiple specialized services:
    - BaseCreditService: Core credit operations
    - PlanService: Plan-related operations
    - TransactionService: Transaction-related operations
    - SubscriptionService: Subscription-related operations
    - StripeIntegrationService: Stripe integration operations
    
    By delegating to these specialized services, CreditService provides
    a unified interface for all credit-related operations while maintaining
    a modular and maintainable codebase.
    """
    
    def __init__(self, db):
        """Initialize with database session and create service instances."""
        self.db = db
        logger.info("Initializing CreditService", event_type="credit_service_init")
        
        # Initialize services
        self.base_service = BaseCreditService(db)
        self.plan_service = PlanService()
        self.transaction_service = TransactionService()
        self.subscription_service = SubscriptionService()
        self.stripe_service = StripeIntegrationService()
        
        # Set db for all services
        self.plan_service.db = db
        self.transaction_service.db = db
        self.subscription_service.db = db
        self.stripe_service.db = db
        
        # Set dependencies between services
        self.transaction_service.plan_service = self.plan_service
        self.transaction_service.base_service = self.base_service
        self.transaction_service.stripe_service = self.stripe_service
        
        self.subscription_service.plan_service = self.plan_service
        self.subscription_service.base_service = self.base_service
        self.subscription_service.stripe_service = self.stripe_service
        
    # Delegate BaseCreditService methods
    async def get_user_credit(self, user_id):
        logger.debug(f"Getting user credit: User {user_id}", event_type="get_user_credit", user_id=user_id)
        return await self.base_service.get_user_credit(user_id)
        
    async def add_credits(self, **kwargs):
        user_id = kwargs.get('user_id')
        amount = kwargs.get('amount')
        logger.debug(f"Adding credits: User {user_id}, Amount {amount}", 
                   event_type="add_credits", 
                   user_id=user_id, 
                   amount=amount)
        return await self.base_service.add_credits(**kwargs)
        
    async def use_credits(self, **kwargs):
        user_id = kwargs.get('user_id')
        amount = kwargs.get('amount')
        logger.debug(f"Using credits: User {user_id}, Amount {amount}", 
                   event_type="use_credits", 
                   user_id=user_id, 
                   amount=amount)
        return await self.base_service.use_credits(**kwargs)
        
    async def get_balance(self, user_id):
        logger.debug(f"Getting balance: User {user_id}", event_type="get_balance", user_id=user_id)
        return await self.base_service.get_balance(user_id)
        
    async def get_transaction_history(self, **kwargs):
        user_id = kwargs.get('user_id')
        logger.debug(f"Getting transaction history: User {user_id}", 
                   event_type="get_transaction_history", 
                   user_id=user_id)
        return await self.base_service.get_transaction_history(**kwargs)
        
    # Delegate PlanService methods
    async def get_plan_by_id(self, plan_id):
        logger.debug(f"Getting plan by ID: {plan_id}", event_type="get_plan_by_id", plan_id=plan_id)
        return await self.plan_service.get_plan_by_id(plan_id)
        
    async def get_active_subscription(self, user_id):
        logger.debug(f"Getting active subscription: User {user_id}", 
                   event_type="get_active_subscription", 
                   user_id=user_id)
        return await self.plan_service.get_active_subscription(user_id)
        
    async def get_subscription_by_id(self, subscription_id):
        logger.debug(f"Getting subscription by ID: {subscription_id}", 
                   event_type="get_subscription_by_id", 
                   subscription_id=subscription_id)
        return await self.plan_service.get_subscription_by_id(subscription_id)
        
    async def get_user_subscriptions(self, **kwargs):
        user_id = kwargs.get('user_id')
        logger.debug(f"Getting user subscriptions: User {user_id}", 
                   event_type="get_user_subscriptions", 
                   user_id=user_id)
        return await self.plan_service.get_user_subscriptions(**kwargs)
        
    async def get_subscription_by_stripe_id(self, stripe_subscription_id):
        logger.debug(f"Getting subscription by Stripe ID: {stripe_subscription_id}", 
                   event_type="get_subscription_by_stripe_id", 
                   stripe_subscription_id=stripe_subscription_id)
        return await self.plan_service.get_subscription_by_stripe_id(stripe_subscription_id)
        
    async def get_all_active_plans(self):
        logger.debug("Getting all active plans", event_type="get_all_active_plans")
        return await self.plan_service.get_all_active_plans()
        
    # Delegate TransactionService methods
    async def purchase_one_time_credits(self, **kwargs):
        user_id = kwargs.get('user_id')
        amount = kwargs.get('amount')
        logger.debug(f"Purchasing one-time credits: User {user_id}, Amount {amount}", 
                   event_type="purchase_one_time_credits", 
                   user_id=user_id, 
                   amount=amount)
        return await self.transaction_service.purchase_one_time_credits(**kwargs)
    
    async def verify_and_process_one_time_payment(self, **kwargs):
        user_id = kwargs.get('user_id')
        transaction_id = kwargs.get('transaction_id')
        logger.debug(f"Verifying and processing one-time payment: User {user_id}, Transaction {transaction_id}", 
                   event_type="verify_and_process_one_time_payment", 
                   user_id=user_id, 
                   transaction_id=transaction_id)
        return await self.transaction_service.verify_and_process_one_time_payment(**kwargs)
        
    async def purchase_plan(self, **kwargs):
        user_id = kwargs.get('user_id')
        plan_id = kwargs.get('plan_id')
        logger.debug(f"Purchasing plan: User {user_id}, Plan {plan_id}", 
                   event_type="purchase_plan", 
                   user_id=user_id, 
                   plan_id=plan_id)
        return await self.transaction_service.purchase_plan(**kwargs)
    
    async def verify_and_process_subscription(self, **kwargs):
        user_id = kwargs.get('user_id')
        transaction_id = kwargs.get('transaction_id')
        logger.debug(f"Verifying and processing subscription: User {user_id}, Transaction {transaction_id}", 
                   event_type="verify_and_process_subscription", 
                   user_id=user_id, 
                   transaction_id=transaction_id)
        return await self.transaction_service.verify_and_process_subscription(**kwargs)
        
    # Delegate SubscriptionService methods
    async def renew_subscription(self, **kwargs):
        subscription_id = kwargs.get('subscription_id')
        logger.debug(f"Renewing subscription: {subscription_id}", 
                   event_type="renew_subscription", 
                   subscription_id=subscription_id)
        return await self.subscription_service.renew_subscription(**kwargs)
        
    async def upgrade_plan(self, **kwargs):
        user_id = kwargs.get('user_id')
        current_subscription_id = kwargs.get('current_subscription_id')
        new_plan_id = kwargs.get('new_plan_id')
        logger.debug(f"Upgrading plan: User {user_id}, Subscription {current_subscription_id}, New Plan {new_plan_id}", 
                   event_type="upgrade_plan", 
                   user_id=user_id, 
                   current_subscription_id=current_subscription_id, 
                   new_plan_id=new_plan_id)
        return await self.subscription_service.upgrade_plan(**kwargs)
        
    async def update_subscription_auto_renew(self, **kwargs):
        subscription_id = kwargs.get('subscription_id')
        auto_renew = kwargs.get('auto_renew')
        logger.debug(f"Updating subscription auto-renew: {subscription_id}, Auto-renew {auto_renew}", 
                   event_type="update_subscription_auto_renew", 
                   subscription_id=subscription_id, 
                   auto_renew=auto_renew)
        return await self.subscription_service.update_subscription_auto_renew(**kwargs)
        
    async def update_subscription_status(self, **kwargs):
        stripe_subscription_id = kwargs.get('stripe_subscription_id')
        status = kwargs.get('status')
        logger.debug(f"Updating subscription status: {stripe_subscription_id}, Status {status}", 
                   event_type="update_subscription_status", 
                   stripe_subscription_id=stripe_subscription_id, 
                   status=status)
        return await self.subscription_service.update_subscription_status(**kwargs)
        
    # Delegate StripeIntegrationService methods
    async def get_user_by_stripe_customer_id(self, stripe_customer_id):
        logger.debug(f"Getting user by Stripe customer ID: {stripe_customer_id}", 
                   event_type="get_user_by_stripe_customer_id", 
                   stripe_customer_id=stripe_customer_id)
        return await self.stripe_service.get_user_by_stripe_customer_id(stripe_customer_id)
    
    async def verify_transaction_id(self, transaction_id):
        logger.debug(f"Verifying transaction ID: {transaction_id}", 
                   event_type="verify_transaction_id", 
                   transaction_id=transaction_id)
        return await self.stripe_service.verify_transaction_id(transaction_id)
    
    async def check_active_subscription(self, user_id):
        logger.debug(f"Checking active subscription: User {user_id}", 
                   event_type="check_active_subscription", 
                   user_id=user_id)
        return await self.stripe_service.check_active_subscription(user_id)
    
    async def cancel_subscription(self, stripe_subscription_id=None, subscription_id=None, cancel_in_stripe=True):
        """
        Cancel a subscription either by Stripe subscription ID or by internal subscription ID.
        
        Args:
            stripe_subscription_id: The Stripe subscription ID (optional)
            subscription_id: The internal subscription ID (optional)
            cancel_in_stripe: Whether to also cancel the subscription in Stripe (default: True)
            
        Returns:
            bool: True if cancellation was successful, False otherwise
            
        Note:
            Either stripe_subscription_id or subscription_id must be provided.
        """
        if subscription_id is not None:
            logger.debug(f"Cancelling subscription by ID: {subscription_id}",
                       event_type="cancel_subscription_by_id",
                       subscription_id=subscription_id,
                       cancel_in_stripe=cancel_in_stripe)
            return await self.subscription_service.cancel_subscription(
                subscription_id=subscription_id,
                cancel_in_stripe=cancel_in_stripe
            )
        elif stripe_subscription_id is not None:
            logger.debug(f"Cancelling subscription by Stripe ID: {stripe_subscription_id}",
                       event_type="cancel_subscription_by_stripe_id",
                       stripe_subscription_id=stripe_subscription_id)
            return await self.stripe_service.cancel_subscription(stripe_subscription_id)
        else:
            logger.error("No subscription ID provided for cancellation",
                       event_type="cancel_subscription_error")
            return False
    
    async def verify_subscription_active(self, stripe_subscription_id):
        logger.debug(f"Verifying subscription active: {stripe_subscription_id}", 
                   event_type="verify_subscription_active", 
                   stripe_subscription_id=stripe_subscription_id)
        return await self.stripe_service.verify_subscription_active(stripe_subscription_id)


# Export the main service class and exceptions
__all__ = ['CreditService', 'InsufficientCreditsError']