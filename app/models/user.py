"""SQLAlchemy models for user-related database tables including User and PasswordResetToken."""

# app/models/user.py
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime

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
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)


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
    expires_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    used = Column(Boolean, default=False, nullable=False)
