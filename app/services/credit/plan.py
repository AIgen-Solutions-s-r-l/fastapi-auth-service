"""Plan-related functionality for the credit service."""

from typing import Optional, List
from sqlalchemy import select, and_, desc

from app.models.plan import Plan, Subscription
# Remove BaseCreditService import and inheritance
# from app.services.credit.base import BaseCreditService


class PlanService: # Removed inheritance
    """Service class for plan-related operations."""

    async def get_plan_by_id(self, plan_id: int) -> Optional[Plan]:
        """
        Get plan by ID.

        Args:
            plan_id: ID of the plan to retrieve

        Returns:
            Optional[Plan]: The plan if found, None otherwise
        """
        result = await self.db.execute(
            select(Plan).where(and_(
                Plan.id == plan_id,
                Plan.is_active == True  # noqa: E712
            ))
        )
        return result.scalar_one_or_none()

    async def get_active_subscription(self, user_id: int) -> Optional[Subscription]:
        """
        Get user's active subscription if any.

        Args:
            user_id: ID of the user

        Returns:
            Optional[Subscription]: The active subscription if found, None otherwise
        """
        result = await self.db.execute(
            select(Subscription)
            .where(and_(
                Subscription.user_id == user_id,
                Subscription.is_active == True  # noqa: E712
            ))
            .order_by(desc(Subscription.renewal_date))
        )
        return result.scalar_one_or_none()

    async def get_subscription_by_id(self, subscription_id: int) -> Optional[Subscription]:
        """
        Get subscription by ID.
        
        Args:
            subscription_id: The ID of the subscription to retrieve
            
        Returns:
            Optional[Subscription]: The subscription if found, None otherwise
        """
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_user_subscriptions(
        self, 
        user_id: int, 
        include_inactive: bool = False
    ) -> List[Subscription]:
        """
        Get user's subscriptions.
        
        Args:
            user_id: The ID of the user
            include_inactive: Whether to include inactive subscriptions
            
        Returns:
            List[Subscription]: List of subscriptions for the user
        """
        query = select(Subscription).where(Subscription.user_id == user_id)
        
        if not include_inactive:
            query = query.where(Subscription.is_active == True)  # noqa: E712
            
        query = query.order_by(desc(Subscription.created_at))
        
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_subscription_by_stripe_id(self, stripe_subscription_id: str) -> Optional[Subscription]:
        """
        Get subscription by Stripe subscription ID.
        
        Args:
            stripe_subscription_id: The Stripe subscription ID
            
        Returns:
            Optional[Subscription]: The subscription if found, None otherwise
        """
        result = await self.db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_all_active_plans(self) -> List[Plan]:
        """
        Get all active plans.
        
        Returns:
            List[Plan]: List of active plans
        """
        result = await self.db.execute(
            select(Plan)
            .where(Plan.is_active == True)  # noqa: E712
            .order_by(Plan.price)
        )
        return result.scalars().all()