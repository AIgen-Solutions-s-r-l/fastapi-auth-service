"""SQLAlchemy models for user-related database tables including User and PasswordResetToken."""

from datetime import datetime, UTC
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.core.base import Base


class User(Base):
    """
    SQLAlchemy model representing a user in the database.

    Attributes:
        id (int): The primary key for the user.
        username (str): Unique username for the user.
        email (str): Unique email for the user.
        hashed_password (str): Hashed password for the user.
        is_admin (bool): Flag indicating if user has admin privileges.
        is_verified (bool): Flag indicating if email has been verified.
        verification_token (str): Token for email verification.
        verification_token_expires_at (datetime): Expiration time for verification token.
        stripe_customer_id (str): Stripe customer ID for payment processing.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)

    # Relationships
    credits = relationship("UserCredit", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    """
    SQLAlchemy model representing a password reset token.
    
    Attributes:
        token (str): The unique token string used for password reset.
        user_id (int): Foreign key reference to the user requesting reset.
        expires_at (datetime): Timestamp when the token expires.
        used (bool): Flag indicating if token has been used.
    """
    __tablename__ = "password_reset_tokens"

    token = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    used = Column(Boolean, default=False, nullable=False)


class EmailVerificationToken(Base):
    """
    SQLAlchemy model representing an email verification token.
    
    Attributes:
        token (str): The unique token string used for email verification.
        user_id (int): Foreign key reference to the user being verified.
        expires_at (datetime): Timestamp when the token expires.
        used (bool): Flag indicating if token has been used.
    """
    __tablename__ = "email_verification_tokens"

    token = Column(String(255), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    used = Column(Boolean, default=False, nullable=False)
    
    # Relationship
    user = relationship("User")
