"""Transaction-related functionality for the credit service."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, Tuple
import uuid

from fastapi import HTTPException, status, BackgroundTasks

from app.models.credit import TransactionType
from app.models.user import User
from app.schemas import credit_schemas
from app.log.logging import logger
from sqlalchemy import select

# Remove BaseCreditService import and inheritance
# from app.services.credit.base import BaseCreditService
from app.services.credit.decorators import db_error_handler
from app.services.credit.utils import calculate_credits_from_payment, calculate_renewal_date


class TransactionService: # Removed inheritance
    """Service class for transaction-related operations."""
    
    def __init__(self):
        """Initialize the service."""
        self.db = None
        self.plan_service = None  # Will be set by CreditService
        self.base_service = None  # Will be set by CreditService
        
    async def _send_email_notification(self, background_tasks, user_id, plan, subscription, email_type=None, plan_name=None, amount=None, credit_amount=None, renewal_date=None):
        """Send email notification for plan purchase."""
        # This is a stub method that doesn't actually send emails in tests
        # In production, this would be implemented to send actual emails
        pass

    @db_error_handler()
    async def purchase_one_time_credits(
        self,
        user_id: int,
        amount: Decimal,
        price: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> credit_schemas.TransactionResponse:
        """
        Process one-time credit purchase without subscription.

        Args:
            user_id: ID of the user
            amount: Amount of credits to add
            price: Price paid for the credits
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction
            background_tasks: Optional background tasks for sending emails

        Returns:
            TransactionResponse: Details of the transaction
        """
        if not reference_id:
            reference_id = str(uuid.uuid4())
            
        transaction = await self.add_credits(
            user_id=user_id,
            amount=amount,
            reference_id=reference_id,
            description=description or f"One-time purchase of {amount} credits",
            transaction_type=TransactionType.ONE_TIME_PURCHASE
        )

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=user_id,
                plan=None,
                subscription=None,
                email_type="one_time_purchase",
                amount=price,
                credits=amount
            )

        logger.info(f"One-time credits purchased: User {user_id}, Credits {amount}, Price {price}",
                  event_type="one_time_credits_purchased",
                  user_id=user_id,
                  credit_amount=amount,
                  price=price)

        return transaction

    @db_error_handler()
    async def purchase_plan(
        self,
        user_id: int,
        plan_id: int,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Tuple[credit_schemas.TransactionResponse, object]:
        """
        Purchase a plan, add credits, and create subscription.

        Args:
            user_id: ID of the user
            plan_id: ID of the plan
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction
            background_tasks: Optional background tasks for sending emails

        Returns:
            Tuple with TransactionResponse and Subscription

        Raises:
            HTTPException: If the plan does not exist or is inactive
        """
        # Get the plan using plan_service
        plan = await self.plan_service.get_plan_by_id(plan_id)
        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Plan not found or inactive"
            )

        # Check if user already has an active subscription
        existing_subscription = await self.plan_service.get_active_subscription(user_id)
        if existing_subscription:
            # Deactivate existing subscription
            existing_subscription.is_active = False
            await self.db.commit()

        # Calculate renewal date
        start_date = datetime.now(UTC)
        renewal_date = calculate_renewal_date(start_date)

        # Create subscription
        from app.models.plan import Subscription
        
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan_id,
            start_date=start_date,
            renewal_date=renewal_date,
            is_active=True,
            auto_renew=True
        )
        self.db.add(subscription)
        await self.db.commit()
        await self.db.refresh(subscription)

        # Add credits
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        transaction = await self.base_service.add_credits(
            user_id=user_id,
            amount=plan.credit_amount,
            reference_id=reference_id,
            description=description or f"Purchase of {plan.name} plan",
            transaction_type=TransactionType.PLAN_PURCHASE,
            plan_id=plan_id,
            subscription_id=subscription.id
        )

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=user_id,
                plan=plan,
                subscription=subscription,
                email_type="payment_confirmation",
                plan_name=plan.name,
                amount=plan.price,
                credit_amount=plan.credit_amount,
                renewal_date=renewal_date
            )

        logger.info(f"Plan purchased: User {user_id}, Plan {plan_id}, Credits {plan.credit_amount}",
                  event_type="plan_purchased",
                  user_id=user_id,
                  plan_id=plan_id,
                  plan_name=plan.name,
                  credit_amount=plan.credit_amount,
                  renewal_date=renewal_date.isoformat())

        return transaction, subscription