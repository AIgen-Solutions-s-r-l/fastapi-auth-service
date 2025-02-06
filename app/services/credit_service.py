"""Service layer for managing user credits."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.schemas import credit_schemas


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
            logger.info(f"Created new credit record for user {user_id}")

        return credit

    async def add_credits(
        self, 
        user_id: int, 
        amount: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> credit_schemas.TransactionResponse:
        """
        Add credits to user's balance.

        Args:
            user_id: The ID of the user
            amount: Amount to add
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction

        Returns:
            TransactionResponse: Details of the transaction
        """
        try:
            credit = await self.get_user_credit(user_id)
            credit.balance += amount
            credit.updated_at = datetime.utcnow()

            transaction = CreditTransaction(
                user_id=user_id,
                amount=amount,
                transaction_type=TransactionType.CREDIT_ADDED,
                reference_id=reference_id,
                description=description
            )

            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)

            logger.info(f"Added {amount} credits to user {user_id}. New balance: {credit.balance}")

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
            logger.error(f"Database error while adding credits: {str(e)}")
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
                logger.warning(
                    f"Insufficient credits for user {user_id}. "
                    f"Required: {amount}, Available: {credit.balance}"
                )
                raise InsufficientCreditsError(
                    f"Insufficient credits. Required: {amount}, Available: {credit.balance}"
                )

            credit.balance -= amount
            credit.updated_at = datetime.utcnow()

            transaction = CreditTransaction(
                user_id=user_id,
                amount=amount,
                transaction_type=TransactionType.CREDIT_USED,
                reference_id=reference_id,
                description=description
            )

            self.db.add(transaction)
            await self.db.commit()
            await self.db.refresh(transaction)

            logger.info(f"Used {amount} credits from user {user_id}. New balance: {credit.balance}")

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
            logger.error(f"Database error while using credits: {str(e)}")
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