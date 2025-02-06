"""SQLAlchemy models for user credit system."""

from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Text
from sqlalchemy.orm import relationship

from app.core.base import Base


class TransactionType(str, Enum):
    """Enum for credit transaction types."""
    PURCHASE = "purchase"
    CREDIT_ADDED = "credit_added"
    CREDIT_USED = "credit_used"
    CREDIT_EXPIRED = "credit_expired"
    REFUND = "refund"


class UserCredit(Base):
    """
    SQLAlchemy model representing a user's credit balance.

    Attributes:
        id (int): The primary key.
        user_id (int): Foreign key reference to the user.
        balance (Numeric): Current credit balance.
        created_at (datetime): Timestamp when the record was created.
        updated_at (datetime): Timestamp when the record was last updated.
    """
    __tablename__ = "user_credits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Numeric(10, 2), default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationship
    user = relationship("User", backref="credit", uselist=False)


class CreditTransaction(Base):
    """
    SQLAlchemy model for tracking credit transactions.

    Attributes:
        id (int): The primary key.
        user_id (int): Foreign key reference to the user.
        amount (Numeric): Transaction amount.
        transaction_type (TransactionType): Type of transaction.
        reference_id (str): External reference ID (e.g., order ID).
        description (str): Transaction description.
        created_at (datetime): Timestamp when the transaction occurred.
    """
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    transaction_type = Column(String(20), nullable=False)
    reference_id = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", backref="credit_transactions")