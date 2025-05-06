"""SQLAlchemy models for user-related database tables including User, PasswordResetToken, and EmailChangeRequest."""

from datetime import datetime, UTC, timedelta
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.core.base_model import Base # Import from new location


class User(Base):
    """
    SQLAlchemy model representing a user in the database.

    Attributes:
        id (int): The primary key for the user.
        email (str): Unique email for the user (primary identifier).
        hashed_password (str): Hashed password for the user.
        is_admin (bool): Flag indicating if user has admin privileges.
        is_verified (bool): Flag indicating if email has been verified.
        verification_token (str): Token for email verification.
        verification_token_expires_at (datetime): Expiration time for verification token.
        stripe_customer_id (str): Stripe customer ID for payment processing.
        google_id (str): Google OAuth user ID for OAuth authentication.
        auth_type (str): Authentication type - "password", "google", or "both".
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Made nullable for OAuth-only users
    google_id = Column(String(255), nullable=True, unique=True)
    auth_type = Column(String(20), default="password", nullable=False)  # "password", "google", "both"
    is_admin = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)) # Also adding updated_at for good practice

    # --- NEW FIELDS for Free Trial Feature ---
    account_status = Column(String(20), default="active", nullable=False, index=True)
    # Options: "trialing", "active", "frozen", "canceled". Indexed for faster queries.

    has_consumed_initial_trial = Column(Boolean, default=False, nullable=False, index=True)
    # Flag to ensure the 10 initial trial credits are granted only once per user. Indexed.
    # This helps with FR-3 idempotency.
    # --- END NEW FIELDS ---

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


class EmailChangeRequest(Base):
    """
    SQLAlchemy model for tracking email change requests.
    
    Attributes:
        id (int): Primary key
        user_id (int): Foreign key reference to the user requesting the change
        current_email (str): Current email address
        new_email (str): Requested new email address
        token (str): Verification token
        expires_at (datetime): Expiration timestamp for the token
        created_at (datetime): When the request was created
        completed (bool): Whether the request has been completed
    """
    __tablename__ = "email_change_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    current_email = Column(String(100), nullable=False)
    new_email = Column(String(100), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    completed = Column(Boolean, default=False, nullable=False)
    
    # Relationship
    user = relationship("User")
