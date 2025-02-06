"""Service layer for managing user credits."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.credit import UserCredit, CreditTransaction, TransactionType
from app.schemas import credit_schemas


class InsufficientCreditsError(Exception):
    """Raised when user has insufficient credits for a transaction."""
    pass


class CreditService:
    """Service class for managing user credits."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def get_user_credit(self, user_id: int) -> UserCredit:
        """
        Get or create user credit record.

        Args:
            user_id: The ID of the user

        Returns:
            UserCredit: The user's credit record
        """
        credit = (
            self.db.query(UserCredit)
            .filter(UserCredit.user_id == user_id)
            .first()
        )

        if not credit:
            credit = UserCredit(user_id=user_id, balance=Decimal('0.00'))
            self.db.add(credit)
            self.db.commit()
            self.db.refresh(credit)
            logger.info(f"Created new credit record for user {user_id}")

        return credit

    def add_credits(
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
            credit = self.get_user_credit(user_id)
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
            self.db.commit()
            self.db.refresh(transaction)

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
            self.db.rollback()
            logger.error(f"Database error while adding credits: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing credit addition"
            )

    def use_credits(
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
            credit = self.get_user_credit(user_id)

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
            self.db.commit()
            self.db.refresh(transaction)

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
            self.db.rollback()
            logger.error(f"Database error while using credits: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error processing credit usage"
            )

    def get_balance(self, user_id: int) -> credit_schemas.CreditBalanceResponse:
        """
        Get user's current credit balance.

        Args:
            user_id: The ID of the user

        Returns:
            CreditBalanceResponse: Current balance and last update time
        """
        credit = self.get_user_credit(user_id)
        return credit_schemas.CreditBalanceResponse(
            user_id=user_id,
            balance=credit.balance,
            updated_at=credit.updated_at
        )

    def get_transaction_history(
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
        total_count = (
            self.db.query(CreditTransaction)
            .filter(CreditTransaction.user_id == user_id)
            .count()
        )

        transactions = (
            self.db.query(CreditTransaction)
            .filter(CreditTransaction.user_id == user_id)
            .order_by(desc(CreditTransaction.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

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
                    new_balance=self.get_user_credit(user_id).balance
                )
                for tx in transactions
            ],
            total_count=total_count
        )