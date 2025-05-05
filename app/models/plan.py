"""Models for plan and subscription management."""

from datetime import datetime, UTC
from sqlalchemy import (
    Column, Integer, String, Numeric, ForeignKey, DateTime, Boolean,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from decimal import Decimal

from app.core.base import Base


class Plan(Base):
    """
    SQLAlchemy model representing a credit plan.
    
    Attributes:
        id (int): The primary key for the plan.
        name (str): Name of the plan.
        credit_amount (Decimal): Amount of credits provided by the plan.
        price (Decimal): Price of the plan.
        is_active (bool): Flag indicating if the plan is currently active.
        description (str): Optional description of the plan.
    """
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    credit_amount = Column(Numeric(10, 2), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    
    # Stripe integration
    stripe_price_id = Column(String(100), nullable=True)
    stripe_product_id = Column(String(100), nullable=True)
    is_limited_free = Column(Boolean, default=False, nullable=False, server_default='false') # Added for Free Plan limitation

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """
    SQLAlchemy model representing a user subscription to a plan.
    
    Attributes:
        id (int): The primary key for the subscription.
        user_id (int): Foreign key reference to the subscribed user.
        plan_id (int): Foreign key reference to the subscribed plan.
        start_date (datetime): Date when the subscription started.
        renewal_date (datetime): Date when the subscription will renew.
        is_active (bool): Flag indicating if the subscription is currently active.
        auto_renew (bool): Flag indicating if the subscription should automatically renew.
        last_renewal_date (datetime): Date when the subscription was last renewed.
    """
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    renewal_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    auto_renew = Column(Boolean, default=True, nullable=False)
    last_renewal_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="active", nullable=False)
    
    # Stripe integration
    stripe_subscription_id = Column(String(100), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")


class UsedFreePlanCard(Base):
    """
    Tracks credit card fingerprints used for limited free plans to enforce uniqueness.
    """
    __tablename__ = "used_free_plan_cards"

    id = Column(Integer, primary_key=True, index=True)
    stripe_card_fingerprint = Column(String(255), nullable=False)
    stripe_payment_method_id = Column(String(100), nullable=True) # Optional reference
    stripe_subscription_id = Column(String(100), nullable=True) # Nullable initially, filled when subscription confirmed
    stripe_customer_id = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint('stripe_card_fingerprint', name='uq_stripe_card_fingerprint'),
        Index('ix_used_free_plan_cards_stripe_card_fingerprint', 'stripe_card_fingerprint'),
        Index('ix_used_free_plan_cards_stripe_payment_method_id', 'stripe_payment_method_id'),
        Index('ix_used_free_plan_cards_stripe_subscription_id', 'stripe_subscription_id'),
        Index('ix_used_free_plan_cards_stripe_customer_id', 'stripe_customer_id'),
    )