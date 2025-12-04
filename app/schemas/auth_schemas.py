"""Pydantic models for authentication-related request and response schemas."""

import re
from typing import Optional, List
from datetime import datetime # Added for datetime type hint
from enum import Enum # Added for SubscriptionStatusEnum
from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator


def validate_password_complexity(password: str) -> List[str]:
    """
    Validate password complexity requirements.
    Returns a list of validation errors, empty if password is valid.

    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    """
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")

    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r'\d', password):
        errors.append("Password must contain at least one digit")

    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~;\'']', password):
        errors.append("Password must contain at least one special character (!@#$%^&*(),.?\":{}|<>_-+=[]\\/'`~;)")

    return errors

class GoogleAuthRequest(BaseModel):
    """Request to initiate Google OAuth flow."""
    redirect_uri: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class GoogleAuthCallback(BaseModel):
    """Callback from Google OAuth."""
    code: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class OAuthProfile(BaseModel):
    """OAuth provider user profile."""
    provider: str
    provider_user_id: str
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class AccountLinkRequest(BaseModel):
    """Request to link OAuth account to existing user."""
    provider: str
    code: str
    password: str
    
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    """Pydantic model for creating a new user."""
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        description="Password must be at least 8 characters with uppercase, lowercase, digit, and special character"
    )
    email_verification_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """Validate password complexity requirements."""
        errors = validate_password_complexity(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class Token(BaseModel):
    """Pydantic model for token response."""
    access_token: str
    token_type: str

    model_config = ConfigDict(from_attributes=True)


class RefreshToken(BaseModel):
    """Pydantic model for token refresh request."""
    token: str

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    """Pydantic model for password change request."""
    current_password: str
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password must meet complexity requirements"
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        """Validate new password complexity requirements."""
        # Skip validation for empty string to let the API handle it with proper error message
        if v == '':
            return v

        errors = validate_password_complexity(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr


class PasswordReset(BaseModel):
    """Schema for password reset with token."""
    token: str
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password must meet complexity requirements"
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        """Validate new password complexity requirements."""
        errors = validate_password_complexity(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class EmailChange(BaseModel):
    """Pydantic model for email change request."""
    new_email: EmailStr
    current_password: str

    model_config = ConfigDict(from_attributes=True)


class VerifyEmail(BaseModel):
    """Schema for email verification."""
    token: str

    model_config = ConfigDict(from_attributes=True)


class ResendVerification(BaseModel):
    """Schema for resending verification email."""
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    """Schema for user response data."""
    email: EmailStr
    is_verified: bool
    auth_type: str

    model_config = ConfigDict(from_attributes=True)


class RegistrationResponse(BaseModel):
    """Schema for registration response."""
    message: str
    email: EmailStr
    verification_sent: bool

    model_config = ConfigDict(from_attributes=True)

# --- Schemas for User Status API ---

class SubscriptionStatusEnum(str, Enum):
    """Enum for Stripe subscription statuses."""
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    # Add any other relevant statuses if needed

class SubscriptionStatusResponse(BaseModel):
    """Pydantic model for subscription details in user status response."""
    stripe_subscription_id: str
    status: SubscriptionStatusEnum # Changed from str to SubscriptionStatusEnum
    plan_name: str
    trial_end_date: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool

    model_config = ConfigDict(from_attributes=True)

class UserAccountStatusEnum(str, Enum):
    """Enum for user account statuses."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    FROZEN = "frozen"
    PENDING_VERIFICATION = "pending_verification"
    NEW_USER = "new_user" # Added status used in tests
    TRIALING = "trialing" # Added status used in tests
    # Add other relevant statuses as needed

class UserStatusResponse(BaseModel):
    """Pydantic model for the user status API response."""
    user_id: str # Assuming this will be the string representation of the UUID
    account_status: UserAccountStatusEnum # Changed from str
    credits_remaining: int
    subscription: Optional[SubscriptionStatusResponse] = None

    model_config = ConfigDict(from_attributes=True)
