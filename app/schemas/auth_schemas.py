# app/core/auth_schemas.py
from pydantic import BaseModel


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
