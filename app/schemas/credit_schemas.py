"""Pydantic schemas for credit-related operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict


class CreditBalanceResponse(BaseModel):
    """Schema for credit balance response."""
    user_id: int
    balance: Decimal
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreditTransactionBase(BaseModel):
    """Base schema for credit transactions."""
    amount: Decimal = Field(..., gt=0, description="Transaction amount must be greater than 0")
    reference_id: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None


class AddCreditRequest(CreditTransactionBase):
    """Schema for adding credits."""
    pass


class UseCreditRequest(CreditTransactionBase):
    """Schema for using credits."""
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amount is positive."""
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v


class TransactionResponse(CreditTransactionBase):
    """Schema for transaction response."""
    id: int
    user_id: int
    transaction_type: str
    created_at: datetime
    new_balance: Decimal
    plan_id: Optional[int] = None
    subscription_id: Optional[int] = None
    is_subscription_active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionHistoryResponse(BaseModel):
    """Schema for transaction history response."""
    transactions: list[TransactionResponse]
    total_count: int


class SubscriptionCancellationRequest(BaseModel):
    """Schema for subscription cancellation request."""
    subscription_id: int = Field(..., description="ID of the subscription to cancel")
    cancel_in_stripe: bool = Field(True, description="Whether to also cancel the subscription in Stripe")


class SubscriptionCancellationResponse(BaseModel):
    """Schema for subscription cancellation response."""
    success: bool = Field(..., description="Whether the cancellation was successful")
    plan_name: Optional[str] = Field(None, description="Name of the cancelled plan")
    effective_end_date: Optional[datetime] = Field(None, description="Date when the subscription will effectively end")
    message: str = Field(..., description="Message describing the result of the cancellation")
    error: Optional[str] = Field(None, description="Error message if cancellation failed")