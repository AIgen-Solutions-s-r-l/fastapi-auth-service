# app/core/auth_schemas.py
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    username: str
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "password": "strongpassword123"
            }
        }


class UserCreate(BaseModel):
    """Pydantic model for creating a new user."""
    username: str
    email: EmailStr
    password: str

    class Config:
        json_schema_extra = {
            "example": {
                "username": "john_doe",
                "email": "john@example.com",
                "password": "strongpassword123"
            }
        }


class Token(BaseModel):
    """Pydantic model for token response."""
    access_token: str
    token_type: str


class PasswordChange(BaseModel):
    """Pydantic model for password change request."""
    current_password: str
    new_password: str

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "oldpassword123",
                "new_password": "newpassword123"
            }
        }
