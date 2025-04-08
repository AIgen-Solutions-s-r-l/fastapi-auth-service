"""Service layer for managing user credits."""

from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Union
from calendar import monthrange
import uuid

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import desc, select, and_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.schemas import credit_schemas
from app.services.email_service import EmailService
from app.log.logging import logger


class InsufficientCreditsError(Exception):
    """Raised when user has insufficient credits for a transaction."""
    pass


class CreditService:
    """Service class for managing user credits."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_user_credit(self, user_id: int) -> UserCredit:
        """
        Get or create user credit record.

        Args:
            user_id: The ID of the user

        Returns:
            UserCredit: The user's credit record
        """
        result = await self.db.execute(
            select(UserCredit).where(UserCredit.user_id == user_id)
        )
        credit = result.scalar_one_or_none()

        if not credit:
            credit = UserCredit(user_id=user_id, balance=Decimal('0.00'))
            self.db.add(credit)
            await self.db.commit()
            await self.db.refresh(credit)
            logger.info(f"Created new credit record for user {user_id}", event_type="credit_record_created", user_id=user_id)

        return credit

    async def add_credits(
        self, 
        user_id: int, 
        amount: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        transaction_type: TransactionType = TransactionType.CREDIT_ADDED,
        plan_id: Optional[int] = None,
        subscription_id: Optional[int] = None
    ) -> credit_schemas.TransactionResponse:
        """
        Add credits to user's balance.

        Args:
            user_id: The ID of the user
            amount: Amount to add
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction
            transaction_type: Type of transaction (default: CREDIT_ADDED)
            plan_id: Optional ID of the plan (for plan purchases)
            subscription_id: Optional ID of the subscription (for plan renewals)

        Returns:
            TransactionResponse: Details of the transaction
        """
        try:
            credit = await self.get_user_credit(user_id)
            credit.balance += amount
            credit.updated_at = datetime.now(UTC)

            transaction = CreditTransaction(
                user_id=user_id,
                user_credit_id=credit.id,
                amount=amount,
                transaction_type=transaction_type,
                reference_id=reference_id,
                description=description,
                plan_id=plan_id,
                subscription_id=subscription_id
            )

            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)

            logger.info(f"Added {amount} credits to user {user_id}. New balance: {credit.balance}", 
                      event_type="credits_added", 
                      user_id=user_id, 
                      amount=amount, 
                      transaction_type=transaction_type,
                      new_balance=credit.balance)

            return credit_schemas.TransactionResponse(
                id=transaction.id,
                user_id=user_id,
                amount=amount,
                transaction_type=transaction.transaction_type,
                reference_id=reference_id,
                description=description,
                created_at=transaction.created_at,
                new_balance=credit.balance
            )

        except IntegrityError as e:
            await self.db.rollback()
            logger.exception(f"Database error while adding credits: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing credit addition"
            )

    async def use_credits(
        self,
        user_id: int,
        amount: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> credit_schemas.TransactionResponse:
        """
        Use credits from user's balance.

        Args:
            user_id: The ID of the user
            amount: Amount to use
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction

        Returns:
            TransactionResponse: Details of the transaction

        Raises:
            InsufficientCreditsError: If user has insufficient credits
        """
        try:
            credit = await self.get_user_credit(user_id)

            if credit.balance < amount:
                logger.warning(f"Insufficient credits for user {user_id}. Required: {amount}, Available: {credit.balance}", 
                             event_type="insufficient_credits", 
                             user_id=user_id, 
                             required=amount, 
                             available=credit.balance)
                raise InsufficientCreditsError(f"Insufficient credits. Required: {amount}, Available: {credit.balance}")

            credit.balance -= amount
            credit.updated_at = datetime.now(UTC)
            transaction = CreditTransaction(
                user_id=user_id,
                user_credit_id=credit.id,
                amount=amount,
                transaction_type=TransactionType.CREDIT_USED,
                reference_id=reference_id,
                description=description
            )

            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)

            logger.info(f"Used {amount} credits from user {user_id}. New balance: {credit.balance}", 
                      event_type="credits_used", 
                      user_id=user_id, 
                      amount=amount, 
                      new_balance=credit.balance)

            return credit_schemas.TransactionResponse(
                id=transaction.id,
                user_id=user_id,
                amount=amount,
                transaction_type=transaction.transaction_type,
                reference_id=reference_id,
                description=description,
                created_at=transaction.created_at,
                new_balance=credit.balance
            )

        except IntegrityError as e:
            await self.db.rollback()
            logger.exception(f"Database error while using credits: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing credit usage"
            )

    async def get_balance(self, user_id: int) -> credit_schemas.CreditBalanceResponse:
        """
        Get user's current credit balance.

        Args:
            user_id: The ID of the user

        Returns:
            CreditBalanceResponse: Current balance and last update time
        """
        credit = await self.get_user_credit(user_id)
        return credit_schemas.CreditBalanceResponse(
            user_id=user_id,
            balance=credit.balance,
            updated_at=credit.updated_at
        )

    async def get_transaction_history(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 50
    ) -> credit_schemas.TransactionHistoryResponse:
        """
        Get user's transaction history.

        Args:
            user_id: The ID of the user
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            TransactionHistoryResponse: List of transactions and total count
        """
        result = await self.db.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user_id)
        )
        total_count = len(result.scalars().all())

        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(desc(CreditTransaction.created_at))
            .offset(skip)
            .limit(limit)
        )
        transactions = result.scalars().all()

        credit = await self.get_user_credit(user_id)
        return credit_schemas.TransactionHistoryResponse(
            transactions=[
                credit_schemas.TransactionResponse(
                    id=tx.id,
                    user_id=tx.user_id,
                    amount=tx.amount,
                    transaction_type=tx.transaction_type,
                    reference_id=tx.reference_id,
                    description=tx.description,
                    created_at=tx.created_at,
                    new_balance=credit.balance
                )
                for tx in transactions
            ],
            total_count=total_count
        )

    async def calculate_renewal_date(self, current_date: datetime) -> datetime:
        """
        Calculate renewal date (same day next month, same hour).

        Args:
            current_date: Current date to calculate from

        Returns:
            datetime: Renewal date

        Notes:
            Handles edge cases like month lengths and leap years.
            If the current day is greater than the last day of the next month,
            the renewal date will be set to the last day of that month.
        """
        try:
            # Get current date components
            year = current_date.year
            month = current_date.month
            day = current_date.day
            hour = current_date.hour
            minute = current_date.minute
            second = current_date.second
            microsecond = current_date.microsecond
            tzinfo = current_date.tzinfo

            # Calculate next month
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year

            # Check days in next month
            _, days_in_next_month = monthrange(next_year, next_month)

            # Handle edge case where current day > days in next month
            if day > days_in_next_month:
                next_day = days_in_next_month
            else:
                next_day = day

            # Create renewal date
            renewal_date = datetime(
                year=next_year,
                month=next_month,
                day=next_day,
                hour=hour,
                minute=minute,
                second=second,
                microsecond=microsecond,
                tzinfo=tzinfo
            )

            return renewal_date

        except Exception as e:
            logger.error(f"Error calculating renewal date: {str(e)}", 
                       event_type="renewal_date_calculation_error", 
                       error=str(e))
            # Fallback to simple 30-day period if calculation fails
            return current_date + timedelta(days=30)

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

    async def purchase_plan(
        self,
        user_id: int,
        plan_id: int,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Tuple[credit_schemas.TransactionResponse, Subscription]:
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
        try:
            # Get the plan
            plan = await self.get_plan_by_id(plan_id)
            if not plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Plan not found or inactive"
                )

            # Check if user already has an active subscription
            existing_subscription = await self.get_active_subscription(user_id)
            if existing_subscription:
                # Deactivate existing subscription
                existing_subscription.is_active = False
                await self.db.commit()

            # Calculate renewal date
            start_date = datetime.now(UTC)
            renewal_date = await self.calculate_renewal_date(start_date)

            # Create subscription
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
            
            transaction = await self.add_credits(
                user_id=user_id,
                amount=plan.credit_amount,
                reference_id=reference_id,
                description=description or f"Purchase of {plan.name} plan",
                transaction_type=TransactionType.PLAN_PURCHASE,
                plan_id=plan_id,
                subscription_id=subscription.id
            )

            # Send email if background_tasks is provided
            if background_tasks:
                # Get user
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Create email service and send confirmation
                    email_service = EmailService(background_tasks, self.db)
                    await email_service.send_payment_confirmation(
                        user=user,
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

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error purchasing plan: {str(e)}",
                       event_type="plan_purchase_error",
                       user_id=user_id,
                       plan_id=plan_id,
                       error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error purchasing plan: {str(e)}"
            )

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

        Raises:
            HTTPException: If the subscription does not exist or renewal fails
        """
        try:
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
            plan = await self.get_plan_by_id(subscription.plan_id)
            if not plan:
                logger.error(f"Plan not found for subscription: {subscription_id}",
                           event_type="plan_not_found",
                           subscription_id=subscription_id,
                           plan_id=subscription.plan_id)
                return None

            # Update subscription
            last_renewal_date = subscription.renewal_date
            subscription.last_renewal_date = last_renewal_date
            subscription.renewal_date = await self.calculate_renewal_date(last_renewal_date)
            await self.db.commit()
            await self.db.refresh(subscription)

            # Add credits
            reference_id = str(uuid.uuid4())
            transaction = await self.add_credits(
                user_id=subscription.user_id,
                amount=plan.credit_amount,
                reference_id=reference_id,
                description=f"Renewal of {plan.name} plan",
                transaction_type=TransactionType.PLAN_RENEWAL,
                plan_id=plan.id,
                subscription_id=subscription.id
            )

            # Send email if background_tasks is provided
            if background_tasks:
                # Get user
                user_result = await self.db.execute(select(User).where(User.id == subscription.user_id))
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Create email service and send confirmation
                    email_service = EmailService(background_tasks, self.db)
                    await email_service.send_payment_confirmation(
                        user=user,
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

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error renewing subscription: {str(e)}",
                       event_type="subscription_renewal_error",
                       subscription_id=subscription_id,
                       error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error renewing subscription: {str(e)}"
            )

    async def upgrade_plan(
        self,
        user_id: int,
        current_subscription_id: int,
        new_plan_id: int,
        reference_id: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> Tuple[credit_schemas.TransactionResponse, Subscription]:
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
        try:
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
            current_plan = await self.get_plan_by_id(current_subscription.plan_id)
            if not current_plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Current plan not found"
                )

            # Get new plan
            new_plan = await self.get_plan_by_id(new_plan_id)
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
            if not reference_id:
                reference_id = str(uuid.uuid4())
                
            transaction = None
            if additional_credits > 0:
                transaction = await self.add_credits(
                    user_id=user_id,
                    amount=additional_credits,
                    reference_id=reference_id,
                    description=f"Upgrade from {current_plan.name} to {new_plan.name}",
                    transaction_type=TransactionType.PLAN_UPGRADE,
                    plan_id=new_plan_id,
                    subscription_id=new_subscription.id
                )

            # Send email if background_tasks is provided
            if background_tasks:
                # Get user
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Create email service and send confirmation
                    email_service = EmailService(background_tasks, self.db)
                    await email_service.send_plan_upgrade(
                        user=user,
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

        except HTTPException as http_ex:
            await self.db.rollback()
            logger.error(f"Error upgrading plan: {http_ex.detail}",
                       event_type="plan_upgrade_error",
                       user_id=user_id,
                       current_subscription_id=current_subscription_id,
                       new_plan_id=new_plan_id,
                       error=http_ex.detail)
            raise http_ex
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error upgrading plan: {str(e)}",
                       event_type="plan_upgrade_error",
                       user_id=user_id,
                       current_subscription_id=current_subscription_id,
                       new_plan_id=new_plan_id,
                       error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error upgrading plan: {str(e)}"
            )

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
        try:
            if not reference_id:
                reference_id = str(uuid.uuid4())
                
            transaction = await self.add_credits(
                user_id=user_id,
                amount=amount,
                reference_id=reference_id,
                description=description or f"One-time purchase of {amount} credits",
                transaction_type=TransactionType.ONE_TIME_PURCHASE
            )

            # Send email if background_tasks is provided
            if background_tasks:
                # Get user
                user_result = await self.db.execute(select(User).where(User.id == user_id))
                user = user_result.scalar_one_or_none()
                
                if user:
                    # Create email service and send confirmation
                    email_service = EmailService(background_tasks, self.db)
                    await email_service.send_one_time_credit_purchase(
                        user=user,
                        amount=price,
                        credits=amount
                    )

            logger.info(f"One-time credits purchased: User {user_id}, Credits {amount}, Price {price}",
                       event_type="one_time_credits_purchased",
                       user_id=user_id,
                       credit_amount=amount,
                       price=price)

            return transaction

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error purchasing one-time credits: {str(e)}",
                       event_type="one_time_purchase_error",
                       user_id=user_id,
                       credit_amount=amount,
                       price=price,
                       error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error purchasing one-time credits: {str(e)}"
            )

    # Methods for Stripe integration and webhook handling

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
        subscription = await self.get_subscription_by_id(subscription_id)
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
        subscription = await self.get_subscription_by_stripe_id(stripe_subscription_id)
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
