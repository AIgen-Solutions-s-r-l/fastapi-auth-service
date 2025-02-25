"""Pydantic schemas for plan-related operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, ConfigDict


class PlanBase(BaseModel):
    """Base schema for plan operations."""
    name: str
    tier: str
    credit_amount: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    description: Optional[str] = None

    @field_validator('credit_amount', 'price')
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        """Ensure amounts are positive."""
        if v <= 0:
            raise ValueError("Value must be greater than 0")
        return v


class PlanCreate(PlanBase):
    """Schema for creating a new plan."""
    is_active: bool = True


class PlanUpdate(BaseModel):
    """Schema for updating an existing plan."""
    name: Optional[str] = None
    tier: Optional[str] = None
    credit_amount: Optional[Decimal] = None
    price: Optional[Decimal] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None

    @field_validator('credit_amount', 'price')
    @classmethod
    def validate_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        """Ensure amounts are positive if provided."""
        if v is not None and v <= 0:
            raise ValueError("Value must be greater than 0")
        return v


class PlanResponse(PlanBase):
    """Schema for plan response."""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanListResponse(BaseModel):
    """Schema for list of plans response."""
    plans: List[PlanResponse]
    count: int


class SubscriptionBase(BaseModel):
    """Base schema for subscription operations."""
    plan_id: int
    auto_renew: bool = True


class SubscriptionCreate(SubscriptionBase):
    """Schema for creating a new subscription."""
    user_id: int


class SubscriptionUpdate(BaseModel):
    """Schema for updating an existing subscription."""
    plan_id: Optional[int] = None
    auto_renew: Optional[bool] = None
    is_active: Optional[bool] = None


class SubscriptionResponse(BaseModel):
    """Schema for subscription response."""
    id: int
    user_id: int
    plan_id: int
    plan_name: str
    plan_tier: str
    credit_amount: Decimal
    start_date: datetime
    renewal_date: datetime
    is_active: bool
    auto_renew: bool
    last_renewal_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionListResponse(BaseModel):
    """Schema for list of subscriptions response."""
    subscriptions: List[SubscriptionResponse]
    count: int


class PlanPurchaseRequest(BaseModel):
    """Schema for purchasing a plan."""
    plan_id: int
    payment_method_id: Optional[str] = None
    reference_id: Optional[str] = None


class PlanUpgradeRequest(BaseModel):
    """Schema for upgrading a plan."""
    current_subscription_id: int
    new_plan_id: int
    payment_method_id: Optional[str] = None
    reference_id: Optional[str] = None


class OneTimePurchaseRequest(BaseModel):
    """Schema for one-time credit purchase."""
    credit_amount: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    payment_method_id: Optional[str] = None
    reference_id: Optional[str] = None

    @field_validator('credit_amount', 'price')
    @classmethod
    def validate_positive(cls, v: Decimal) -> Decimal:
        """Ensure amounts are positive."""
        if v <= 0:
            raise ValueError("Value must be greater than 0")
        return v