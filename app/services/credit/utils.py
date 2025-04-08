"""Utility functions for the credit service module."""

from datetime import datetime, UTC, timedelta
from decimal import Decimal
from calendar import monthrange

from app.log.logging import logger
from app.models.credit import CreditTransaction
from app.schemas import credit_schemas


def create_transaction_response(
    transaction: CreditTransaction, 
    new_balance: Decimal
) -> credit_schemas.TransactionResponse:
    """
    Create a transaction response object from a transaction.
    
    Args:
        transaction: The transaction to create a response from
        new_balance: The new balance after the transaction
        
    Returns:
        TransactionResponse: The transaction response
    """
    return credit_schemas.TransactionResponse(
        id=transaction.id,
        user_id=transaction.user_id,
        amount=transaction.amount,
        transaction_type=transaction.transaction_type,
        reference_id=transaction.reference_id,
        description=transaction.description,
        created_at=transaction.created_at,
        new_balance=new_balance,
        plan_id=transaction.plan_id,
        subscription_id=transaction.subscription_id
    )


def calculate_renewal_date(current_date: datetime) -> datetime:
    """
    Calculate renewal date (same day next month, same hour).

    Args:
        current_date: Current date to calculate from

    Returns:
        datetime: Renewal date
    """
    # Extract date components
    year = current_date.year
    month = current_date.month
    day = current_date.day
    
    # Calculate next month
    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year
    
    # Check days in next month
    _, days_in_next_month = monthrange(next_year, next_month)
    
    # Handle edge case where current day > days in next month
    next_day = min(day, days_in_next_month)
    
    try:
        # Create renewal date with same time components
        renewal_date = current_date.replace(
            year=next_year,
            month=next_month,
            day=next_day
        )
        return renewal_date
    except Exception as e:
        logger.error(f"Error calculating renewal date: {str(e)}", 
                   event_type="renewal_date_calculation_error", 
                   error=str(e))
        # Fallback to simple 30-day period if calculation fails
        return current_date + timedelta(days=30)


def calculate_credits_from_payment(payment_amount: Decimal, plans: list) -> Decimal:
    """
    Calculate credit amount based on payment amount using plan ratios.
    
    Args:
        payment_amount: The payment amount
        plans: List of available plans
        
    Returns:
        Decimal: The calculated credit amount
    """
    if not plans:
        # Fallback to default ratio if no plans found
        return payment_amount * Decimal('10')
        
    # Find plans with similar prices
    similar_plans = sorted(plans, key=lambda p: abs(p.price - payment_amount))
    
    if not similar_plans:
        # Fallback to default ratio if no similar plans found
        return payment_amount * Decimal('10')
        
    # Use the most similar plan's credit-to-price ratio to calculate credits
    best_match = similar_plans[0]
    ratio = best_match.credit_amount / best_match.price
    credit_amount = payment_amount * ratio
    
    logger.info(f"Calculated credits using plan-based ratio",
              event_type="credit_calculation",
              payment_amount=float(payment_amount),
              similar_plan_id=best_match.id,
              ratio=float(ratio),
              credit_amount=float(credit_amount))
              
    return credit_amount