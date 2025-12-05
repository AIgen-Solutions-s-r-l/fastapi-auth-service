"""Webhook response schemas."""

from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field


class WebhookStatus(str, Enum):
    """Webhook processing status."""
    SUCCESS = "success"
    ALREADY_PROCESSED = "already_processed"
    UNHANDLED = "unhandled"
    ERROR = "error"


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    status: WebhookStatus = Field(..., description="Processing status")
    message: str = Field(..., description="Status message")
    event_id: Optional[str] = Field(None, description="Stripe event ID")
    event_type: Optional[str] = Field(None, description="Stripe event type")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "success",
                "message": "Event processed successfully",
                "event_id": "evt_1234567890",
                "event_type": "checkout.session.completed"
            }
        }
    }


class WebhookErrorResponse(BaseModel):
    """Webhook error response."""
    status: WebhookStatus = Field(default=WebhookStatus.ERROR, description="Error status")
    message: str = Field(..., description="Error message")
    event_id: Optional[str] = Field(None, description="Stripe event ID if available")
    event_type: Optional[str] = Field(None, description="Stripe event type if available")
    retry: bool = Field(default=True, description="Whether Stripe should retry this event")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "error",
                "message": "Database connection failed",
                "event_id": "evt_1234567890",
                "event_type": "checkout.session.completed",
                "retry": True
            }
        }
    }


# List of supported webhook event types for documentation
SUPPORTED_WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
]

WEBHOOK_EVENTS_DESCRIPTION = """
## Supported Stripe Webhook Events

This endpoint processes the following Stripe webhook events:

| Event Type | Description |
|------------|-------------|
| `checkout.session.completed` | Payment checkout completed successfully |
| `customer.subscription.created` | New subscription created |
| `customer.subscription.updated` | Subscription status changed |
| `customer.subscription.deleted` | Subscription cancelled or expired |
| `invoice.payment_succeeded` | Invoice payment successful |
| `invoice.payment_failed` | Invoice payment failed |

### Idempotency

All events are processed idempotently. Duplicate events (same event ID) are
detected and safely skipped, returning a success response.

### Retry Behavior

- **2xx responses**: Event processed successfully, no retry
- **4xx responses**: Client error, no retry (invalid signature, etc.)
- **5xx responses**: Server error, Stripe will retry with exponential backoff

### Security

All webhook requests must include a valid `Stripe-Signature` header.
The signature is verified against the configured webhook secret.
"""
