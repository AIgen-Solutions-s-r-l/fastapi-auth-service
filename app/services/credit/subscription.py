"""Subscription-related functionality for the credit service."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, Tuple, List
import uuid

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select, and_, desc

from app.models.credit import TransactionType
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.schemas import credit_schemas
from app.log.logging import logger

# Remove BaseCreditService import and inheritance
# from app.services.credit.base import BaseCreditService
from app.services.credit.decorators import db_error_handler
from app.services.credit.utils import calculate_renewal_date

class SubscriptionService: # Removed inheritance
    """Service class for subscription-related operations."""
    
    def __init__(self):
        """Initialize the service."""
        self.db = None
        self.plan_service = None  # Will be set by CreditService
        self.base_service = None  # Will be set by CreditService


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
    async def upgrade_plan(
        self,
        user_id: int,
        current_subscription_id: int,
        new_plan_id: int,
        reference_id: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Tuple[Optional[credit_schemas.TransactionResponse], Subscription]:
        """
        Upgrade a subscription to a higher plan.

        Args:
            user_id: ID of the user
            current_subscription_id: ID of the current subscription
            new_plan_id: ID of the new plan
            reference_id: Optional reference ID for the transaction
            background_tasks: Optional background tasks for sending emails

        Returns:
            Tuple with TransactionResponse and new Subscription

        Raises:
            HTTPException: If the plans don't exist or upgrade fails
        """
        # Get current subscription
        sub_result = await self.db.execute(
            select(Subscription).where(and_(
                Subscription.id == current_subscription_id,
                Subscription.user_id == user_id,
                Subscription.is_active == True  # noqa: E712
            ))
        )
        current_subscription = sub_result.scalar_one_or_none()
        
        if not current_subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active subscription not found"
            )

        # Get current plan
        current_plan = await self.plan_service.get_plan_by_id(current_subscription.plan_id)
        if not current_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Current plan not found"
            )

        # Get new plan
        new_plan = await self.plan_service.get_plan_by_id(new_plan_id)
        if not new_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="New plan not found or inactive"
            )
            
        # Validate upgrade (ensure new plan is higher priced)
        if new_plan.price <= current_plan.price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New plan must have a higher price than current plan"
            )

        # Deactivate current subscription
        current_subscription.is_active = False
        await self.db.commit()

        # Calculate additional credits
        additional_credits = new_plan.credit_amount - current_plan.credit_amount
        if additional_credits < 0:
            additional_credits = Decimal('0')

        # Create new subscription with same renewal date
        start_date = datetime.now(UTC)
        new_subscription = Subscription(
            user_id=user_id,
            plan_id=new_plan_id,
            start_date=start_date,
            renewal_date=current_subscription.renewal_date,  # Keep the same renewal date
            is_active=True,
            auto_renew=current_subscription.auto_renew
        )
        self.db.add(new_subscription)
        await self.db.commit()
        await self.db.refresh(new_subscription)

        # Add additional credits if there are any
        transaction = None
        if additional_credits > 0:
            if not reference_id:
                reference_id = str(uuid.uuid4())
                
            transaction = await self.base_service.add_credits(
                user_id=user_id,
                amount=additional_credits,
                reference_id=reference_id,
                description=f"Upgrade from {current_plan.name} to {new_plan.name}",
                transaction_type=TransactionType.PLAN_UPGRADE,
                plan_id=new_plan_id,
                subscription_id=new_subscription.id
            )

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=user_id,
                email_type="plan_upgrade",
                old_plan_name=current_plan.name,
                new_plan_name=new_plan.name,
                additional_credits=additional_credits,
                new_renewal_date=new_subscription.renewal_date
            )

        logger.info(f"Plan upgraded: User {user_id}, Old Plan {current_plan.id}, New Plan {new_plan.id}",
                  event_type="plan_upgraded",
                  user_id=user_id,
                  old_plan_id=current_plan.id,
                  old_plan_name=current_plan.name,
                  new_plan_id=new_plan.id,
                  new_plan_name=new_plan.name,
                  additional_credits=additional_credits,
                  renewal_date=new_subscription.renewal_date.isoformat())

        return transaction, new_subscription

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