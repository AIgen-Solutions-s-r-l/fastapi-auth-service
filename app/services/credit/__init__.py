"""Credit service module for managing user credits and subscriptions."""

from app.services.credit.base import BaseCreditService
from app.services.credit.plan import PlanService
from app.services.credit.transaction import TransactionService
from app.services.credit.subscription import SubscriptionService
from app.services.credit.stripe_integration import StripeIntegrationService
from app.services.credit.exceptions import InsufficientCreditsError


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
        self.subscription_service.plan_service = self.plan_service
        self.subscription_service.base_service = self.base_service
        
        # Set up dependencies between services
        self.transaction_service.plan_service = self.plan_service
        self.subscription_service.plan_service = self.plan_service
        
        # Initialize db for all services
        self.plan_service.db = db
        self.transaction_service.db = db
        self.subscription_service.db = db
        self.stripe_service.db = db
        
    # Delegate BaseCreditService methods
    async def get_user_credit(self, user_id):
        return await self.base_service.get_user_credit(user_id)
        
    async def add_credits(self, **kwargs):
        return await self.base_service.add_credits(**kwargs)
        
    async def use_credits(self, **kwargs):
        return await self.base_service.use_credits(**kwargs)
        
    async def get_balance(self, user_id):
        return await self.base_service.get_balance(user_id)
        
    async def get_transaction_history(self, **kwargs):
        return await self.base_service.get_transaction_history(**kwargs)
        
    # Delegate PlanService methods
    async def get_plan_by_id(self, plan_id):
        return await self.plan_service.get_plan_by_id(plan_id)
        
    async def get_active_subscription(self, user_id):
        return await self.plan_service.get_active_subscription(user_id)
        
    async def get_subscription_by_id(self, subscription_id):
        return await self.plan_service.get_subscription_by_id(subscription_id)
        
    async def get_user_subscriptions(self, **kwargs):
        return await self.plan_service.get_user_subscriptions(**kwargs)
        
    async def get_subscription_by_stripe_id(self, stripe_subscription_id):
        return await self.plan_service.get_subscription_by_stripe_id(stripe_subscription_id)
        
    async def get_all_active_plans(self):
        return await self.plan_service.get_all_active_plans()
        
    # Delegate TransactionService methods
    async def purchase_one_time_credits(self, **kwargs):
        return await self.transaction_service.purchase_one_time_credits(**kwargs)
        
    async def purchase_plan(self, **kwargs):
        return await self.transaction_service.purchase_plan(**kwargs)
        
    # Delegate SubscriptionService methods
    async def renew_subscription(self, **kwargs):
        return await self.subscription_service.renew_subscription(**kwargs)
        
    async def upgrade_plan(self, **kwargs):
        return await self.subscription_service.upgrade_plan(**kwargs)
        
    async def update_subscription_auto_renew(self, **kwargs):
        return await self.subscription_service.update_subscription_auto_renew(**kwargs)
        
    async def update_subscription_status(self, **kwargs):
        return await self.subscription_service.update_subscription_status(**kwargs)
        
    # Delegate StripeIntegrationService methods
    async def get_user_by_stripe_customer_id(self, stripe_customer_id):
        return await self.stripe_service.get_user_by_stripe_customer_id(stripe_customer_id)


# Export the main service class and exceptions
__all__ = ['CreditService', 'InsufficientCreditsError']