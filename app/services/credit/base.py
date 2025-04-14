"""Base credit service with core functionality."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Union
import uuid

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import desc, select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.schemas import credit_schemas
from app.services.email_service import EmailService
from app.log.logging import logger

from app.services.credit.decorators import db_error_handler
from app.services.credit.exceptions import InsufficientCreditsError
from app.services.credit.utils import create_transaction_response


class BaseCreditService:
    """Base service class for managing user credits."""

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
            logger.info(f"Created new credit record for user {user_id}", 
                      event_type="credit_record_created", 
                      user_id=user_id)

        return credit

    async def _send_email_notification(
        self,
        background_tasks: BackgroundTasks,
        user_id: int,
        email_type: str,
        **email_params
    ) -> None:
        """
        Send email notification.
        
        Args:
            background_tasks: FastAPI background tasks
            user_id: The ID of the user
            email_type: Type of email to send
            **email_params: Parameters for the email
        """
        if not background_tasks:
            return
            
        # Get user
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User not found for email notification: {user_id}",
                         event_type="email_notification_user_not_found",
                         user_id=user_id)
            return
            
        # Create email service
        email_service = EmailService(background_tasks, self.db)
        
        # Send appropriate email based on type
        if email_type == "payment_confirmation":
            await email_service.send_payment_confirmation(
                user=user,
                **email_params
            )
        elif email_type == "plan_upgrade":
            await email_service.send_plan_upgrade(
                user=user,
                **email_params
            )
        elif email_type == "one_time_purchase":
            await email_service.send_one_time_credit_purchase(
                user=user,
                **email_params
            )

    @db_error_handler()
    async def add_credits(
        self,
        user_id: int,
        amount: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        transaction_type: TransactionType = TransactionType.CREDIT_ADDED,
        plan_id: Optional[int] = None,
        subscription_id: Optional[int] = None,
        monetary_amount: Optional[Decimal] = None,
        currency: str = "USD"
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

        logger.info(f"Adding transaction to database: User {user_id}, Amount {amount}, Type {transaction_type}",
                  event_type="adding_transaction",
                  user_id=user_id,
                  amount=amount,
                  transaction_type=transaction_type,
                  reference_id=reference_id)

        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)

        logger.info(f"Added {amount} credits to user {user_id}. New balance: {credit.balance}, Transaction ID: {transaction.id}",
                  event_type="credits_added",
                  user_id=user_id,
                  amount=amount,
                  transaction_type=transaction_type,
                  new_balance=credit.balance,
                  transaction_id=transaction.id)

        return create_transaction_response(
            transaction,
            credit.balance,
            monetary_amount=monetary_amount,
            currency=currency
        )
    @db_error_handler()
    async def use_credits(
        self,
        user_id: int,
        amount: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        monetary_amount: Optional[Decimal] = None,
        currency: str = "USD"
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

        return create_transaction_response(
            transaction,
            credit.balance,
            monetary_amount=monetary_amount,
            currency=currency
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

    @db_error_handler()
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
        logger.info(f"Getting transaction history for user {user_id}",
                  event_type="get_transaction_history_start",
                  user_id=user_id,
                  skip=skip,
                  limit=limit)

        # Get total count with a single query
        count_result = await self.db.execute(
            select(func.count()).select_from(CreditTransaction).where(
                CreditTransaction.user_id == user_id
            )
        )
        total_count = count_result.scalar_one()

        logger.info(f"Found {total_count} transactions for user {user_id}",
                  event_type="transaction_count",
                  user_id=user_id,
                  total_count=total_count)

        # Get transactions with pagination
        result = await self.db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(desc(CreditTransaction.created_at))
            .offset(skip)
            .limit(limit)
        )
        transactions = result.scalars().all()

        logger.info(f"Retrieved {len(transactions)} transactions for user {user_id}",
                  event_type="transactions_retrieved",
                  user_id=user_id,
                  retrieved_count=len(transactions),
                  transaction_ids=[tx.id for tx in transactions])
                  
        # Log transaction details for debugging
        for tx in transactions:
            logger.info(f"Transaction details: ID {tx.id}, Type {tx.transaction_type}, Amount {tx.amount}, Created {tx.created_at}",
                      event_type="transaction_details",
                      user_id=user_id,
                      transaction_id=tx.id,
                      transaction_type=tx.transaction_type,
                      amount=tx.amount,
                      created_at=tx.created_at,
                      reference_id=tx.reference_id)

        # Get current balance
        credit = await self.get_user_credit(user_id)
        
        # Process transactions to include monetary amounts
        processed_transactions = []
        for tx in transactions:
            monetary_amount = None
            
            # Determine monetary amount based on transaction type
            if tx.transaction_type == TransactionType.ONE_TIME_PURCHASE:
                # For one-time purchases, estimate based on credit amount
                monetary_amount = tx.amount / Decimal('10')  # Default ratio
            elif tx.transaction_type in [TransactionType.PLAN_PURCHASE, TransactionType.PLAN_RENEWAL, TransactionType.PLAN_UPGRADE]:
                # For plan-related transactions, get the plan price if available
                if tx.plan_id:
                    from app.models.plan import Plan
                    plan_result = await self.db.execute(
                        select(Plan).where(Plan.id == tx.plan_id)
                    )
                    plan = plan_result.scalar_one_or_none()
                    if plan:
                        monetary_amount = plan.price
            
            # Create transaction response with monetary amount
            processed_tx = create_transaction_response(
                tx,
                credit.balance,
                monetary_amount=monetary_amount
            )
            processed_transactions.append(processed_tx)
        
        response = credit_schemas.TransactionHistoryResponse(
            transactions=processed_transactions,
            total_count=total_count
        )

        logger.info(f"Returning transaction history response for user {user_id}",
                  event_type="get_transaction_history_complete",
                  user_id=user_id,
                  total_count=total_count,
                  returned_count=len(response.transactions))

        return response