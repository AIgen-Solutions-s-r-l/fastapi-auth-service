"""Credit-related database models."""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship

from app.core.base_model import Base # Import from new location


class TransactionType(str, Enum):
    """Types of credit transactions."""
    CREDIT_ADDED = "credit_added"
    CREDIT_USED = "credit_used"
    PLAN_PURCHASE = "plan_purchase"
    PLAN_RENEWAL = "plan_renewal"
    PLAN_UPGRADE = "plan_upgrade"
    ONE_TIME_PURCHASE = "one_time_purchase"
    TRIAL_CREDIT_GRANT = "trial_credit_grant" # For the initial 10 free trial credits (FR-3)


class UserCredit(Base):
    """User credit balance model."""
    __tablename__ = "user_credits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    balance = Column(Numeric(10, 2), nullable=False, default=Decimal('0.00'))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    # Relationships
    user = relationship("User", back_populates="credits", passive_deletes=True)
    transactions = relationship("CreditTransaction", back_populates="user_credit", cascade="all, delete-orphan")


class CreditTransaction(Base):
    """Credit transaction model."""
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_credit_id = Column(Integer, ForeignKey("user_credits.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    transaction_type = Column(String(20), nullable=False)
    reference_id = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    
    # Additional fields for plan-related transactions
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="credit_transactions")
    user_credit = relationship("UserCredit", back_populates="transactions")
    plan = relationship("Plan", foreign_keys=[plan_id])
    subscription = relationship("Subscription", foreign_keys=[subscription_id])