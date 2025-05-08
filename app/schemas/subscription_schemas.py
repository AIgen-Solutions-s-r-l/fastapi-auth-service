"""Pydantic models for subscription-related request and response schemas."""

from typing import Optional
from pydantic import BaseModel, ConfigDict

class SubscriptionCancelRequest(BaseModel):
    """Pydantic model for subscription cancellation request."""
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionCancelResponse(BaseModel):
    """Pydantic model for subscription cancellation response."""
    message: str
    subscription_status: str

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Generic error response schema."""
    detail: str

    model_config = ConfigDict(from_attributes=True)