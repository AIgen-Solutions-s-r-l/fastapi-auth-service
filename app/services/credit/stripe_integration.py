"""Stripe integration functionality for the credit service."""

from typing import Optional

from sqlalchemy import select
from app.models.user import User
# Remove BaseCreditService import and inheritance
# from app.services.credit.base import BaseCreditService


class StripeIntegrationService: # Removed inheritance
    """Service class for Stripe integration operations."""

    async def get_user_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[User]:
        """
        Get user by Stripe customer ID.
        
        Args:
            stripe_customer_id: The Stripe customer ID
            
        Returns:
            Optional[User]: The user if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.stripe_customer_id == stripe_customer_id)
        )
        return result.scalar_one_or_none()