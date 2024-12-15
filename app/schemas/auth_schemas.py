"""Pydantic models for authentication-related request and response schemas."""

from pydantic import BaseModel, EmailStr, ConfigDict


class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    username: str
    password: str

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    """Pydantic model for creating a new user."""
    username: str
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """Pydantic model for token response."""
    access_token: str
    token_type: str

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    """Pydantic model for password change request."""
    current_password: str
    new_password: str

    model_config = ConfigDict(from_attributes=True)


class PasswordResetRequest(BaseModel):
    """Schema for password reset request."""
    email: EmailStr


class PasswordReset(BaseModel):
    """Schema for password reset with token."""
    token: str
    new_password: str
