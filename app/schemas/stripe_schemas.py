"""Pydantic schemas for Stripe integration."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, EmailStr, validator


class StripeTransactionRequest(BaseModel):
    """
    Schema for requesting transaction details from Stripe.
    
    Attributes:
        transaction_id: Stripe transaction ID (payment_intent, subscription, etc.)
        email: Customer email to use for lookup if transaction_id is not available
        transaction_type: Type of transaction to look for 
        metadata: Additional metadata for the transaction
    """
    transaction_id: Optional[str] = Field(None, description="Stripe transaction ID")
    email: Optional[EmailStr] = Field(None, description="Customer email for lookup")
    transaction_type: str = Field(..., description="Transaction type (oneoff, subscription)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @validator('transaction_type')
    def validate_transaction_type(cls, value):
        """Validate transaction type is one of the supported types."""
        if value not in ['oneoff', 'subscription']:
            raise ValueError('Transaction type must be oneoff or subscription')
        return value
    
    @validator('transaction_id', 'email')
    def validate_transaction_lookup(cls, v, values):
        """Validate either transaction_id or email is provided."""
        if 'transaction_id' not in values and 'email' not in values:
            if not v:
                raise ValueError('Either transaction_id or email must be provided')
        return v


class StripeTransaction(BaseModel):
    """
    Schema for Stripe transaction details.
    
    Attributes:
        transaction_id: Stripe transaction ID
        transaction_type: Type of transaction
        amount: Transaction amount
        customer_id: Stripe customer ID
        customer_email: Customer email
        created_at: Transaction creation time
        subscription_id: Stripe subscription ID (for subscription transactions)
        plan_id: Stripe plan ID (for subscription transactions)
        product_id: Stripe product ID
        metadata: Additional transaction metadata
    """
    transaction_id: str
    transaction_type: str
    amount: Decimal
    customer_id: Optional[str] = None
    customer_email: Optional[str] = None
    created_at: datetime
    subscription_id: Optional[str] = None
    plan_id: Optional[str] = None
    product_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StripeTransactionResponse(BaseModel):
    """
    Schema for Stripe transaction processing response.
    
    Attributes:
        applied: Whether the transaction was applied successfully
        transaction: Transaction details
        credit_transaction_id: ID of the created credit transaction
        subscription_id: ID of the created/updated subscription
        new_balance: New credit balance after transaction
        message: Optional message
    """
    applied: bool
    transaction: StripeTransaction
    credit_transaction_id: Optional[int] = None
    subscription_id: Optional[int] = None
    new_balance: Optional[Decimal] = None
    message: Optional[str] = None


class StripeCustomer(BaseModel):
    """
    Schema for Stripe customer data.
    
    Attributes:
        customer_id: Stripe customer ID
        email: Customer email
        name: Customer name
        metadata: Additional customer metadata
    """
    customer_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StripeSubscription(BaseModel):
    """
    Schema for Stripe subscription data.
    
    Attributes:
        subscription_id: Stripe subscription ID
        customer_id: Stripe customer ID
        status: Subscription status
        current_period_start: Start of current billing period
        current_period_end: End of current billing period
        cancel_at_period_end: Whether subscription will cancel at period end
        plan_id: Stripe plan ID
        amount: Subscription amount
        metadata: Additional subscription metadata
    """
    subscription_id: str
    customer_id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    plan_id: Optional[str] = None
    amount: Optional[Decimal] = None
    metadata: Optional[Dict[str, Any]] = None


class StripeWebhookResponse(BaseModel):
    """
    Schema for Stripe webhook processing response.
    
    Attributes:
        status: Status of webhook processing
        event_id: Stripe event ID
        event_type: Stripe event type
        processed: Whether event was processed
        result: Processing result details
    """
    status: str
    event_id: str
    event_type: str
    processed: bool
    result: Optional[Dict[str, Any]] = None