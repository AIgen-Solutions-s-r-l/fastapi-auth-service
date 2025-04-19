"""Service layer for Stripe integration."""

import stripe
from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, Dict, List, Any, Union
import asyncio
import json

from app.core.config import settings
from app.log.logging import logger


class StripeService:
    """Service class for Stripe integrations."""

    def __init__(self, test_mode: bool = False):
        """
        Initialize the Stripe service.
        
        Args:
            test_mode: If True, skip API key validation for testing purposes
        """
        # Configure Stripe
        if not test_mode:
            # Check if Stripe API key is available as an attribute
            stripe_key = getattr(settings, 'STRIPE_SECRET_KEY', None)
            stripe_version = getattr(settings, 'STRIPE_API_VERSION', None)
            
            # Validate Stripe configuration
            if not stripe_key:
                logger.error("Stripe API key not configured", event_type="stripe_config_error")
                raise ValueError("Stripe API key not configured")
                
            stripe.api_key = stripe_key
            if stripe_version:
                stripe.api_version = stripe_version

    async def find_transaction_by_id(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a Stripe transaction by ID.
        
        Args:
            transaction_id: The transaction ID
            
        Returns:
            Optional[Dict[str, Any]]: Transaction data if found, None otherwise
        """
        try:
            # First try to find as PaymentIntent (one-time purchases)
            try:
                payment_intent = await asyncio.to_thread(
                    stripe.PaymentIntent.retrieve,
                    transaction_id
                )
                
                if payment_intent:
                    customer_email = None
                    customer_id = payment_intent.get('customer')
                    
                    # Extract email from charge data if available
                    if payment_intent.get('charges', {}).get('data'):
                        charge = payment_intent['charges']['data'][0]
                        if charge.get('billing_details', {}).get('email'):
                            customer_email = charge['billing_details']['email']
                    
                    return {
                        "id": payment_intent.id,
                        "object_type": "payment_intent",
                        "amount": Decimal(payment_intent.amount) / 100,  # Convert cents to dollars
                        "customer_id": customer_id,
                        "customer_email": customer_email,
                        "created_at": datetime.fromtimestamp(payment_intent.created, UTC)
                    }
            except Exception as e:
                logger.debug(f"Not a payment intent: {str(e)}", event_type="stripe_lookup_debug")
            
            # Try to find as Subscription
            try:
                subscription = await asyncio.to_thread(
                    stripe.Subscription.retrieve,
                    transaction_id
                )
                
                if subscription:
                    customer_id = subscription.get('customer')
                    customer_email = None
                    
                    # If we have a customer ID, we can look up the customer to get email
                    if customer_id:
                        try:
                            customer = await asyncio.to_thread(
                                stripe.Customer.retrieve,
                                customer_id
                            )
                            if customer:
                                customer_email = customer.get('email')
                        except Exception as e:
                            logger.warning(f"Error retrieving customer: {str(e)}", event_type="stripe_lookup_warning")
                    
                    return {
                        "id": subscription.id,
                        "object_type": "subscription",
                        "customer_id": customer_id,
                        "customer_email": customer_email,
                        "created_at": datetime.fromtimestamp(subscription.created, UTC),
                        "subscription_data": {
                            "status": subscription.status,
                            "current_period_start": datetime.fromtimestamp(subscription.current_period_start, UTC),
                            "current_period_end": datetime.fromtimestamp(subscription.current_period_end, UTC),
                            "items": subscription.items.data
                        }
                    }
            except Exception as e:
                logger.debug(f"Not a subscription: {str(e)}", event_type="stripe_lookup_debug")
            
            # Try to find as Invoice
            try:
                invoice = await asyncio.to_thread(
                    stripe.Invoice.retrieve,
                    transaction_id
                )
                
                if invoice:
                    customer_id = invoice.get('customer')
                    customer_email = invoice.get('customer_email')
                    subscription_id = invoice.get('subscription')
                    
                    return {
                        "id": invoice.id,
                        "object_type": "invoice",
                        "amount": Decimal(invoice.amount_paid) / 100,  # Convert cents to dollars
                        "customer_id": customer_id,
                        "customer_email": customer_email,
                        "subscription_id": subscription_id,
                        "created_at": datetime.fromtimestamp(invoice.created, UTC)
                    }
            except Exception as e:
                logger.debug(f"Not an invoice: {str(e)}", event_type="stripe_lookup_debug")
            
            # Try to find as Charge
            try:
                charge = await asyncio.to_thread(
                    stripe.Charge.retrieve,
                    transaction_id
                )
                
                if charge:
                    customer_id = charge.get('customer')
                    customer_email = None
                    
                    # Extract email from billing details if available
                    if charge.get('billing_details', {}).get('email'):
                        customer_email = charge['billing_details']['email']
                    
                    return {
                        "id": charge.id,
                        "object_type": "charge",
                        "amount": Decimal(charge.amount) / 100,  # Convert cents to dollars
                        "customer_id": customer_id,
                        "customer_email": customer_email,
                        "created_at": datetime.fromtimestamp(charge.created, UTC)
                    }
            except Exception as e:
                logger.debug(f"Not a charge: {str(e)}", event_type="stripe_lookup_debug")
            
            # Transaction not found
            logger.warning(f"Transaction not found: {transaction_id}", event_type="stripe_transaction_not_found")
            return None
            
        except Exception as e:
            logger.error(f"Error finding transaction: {str(e)}", event_type="stripe_lookup_error", error=str(e))
            return None

    async def find_transactions_by_email(self, email: str) -> List[Dict[str, Any]]:
        """
        Find Stripe transactions by customer email.
        
        Args:
            email: The customer email
            
        Returns:
            List[Dict[str, Any]]: List of transactions
        """
        try:
            # First, find customers with this email
            customers = await asyncio.to_thread(
                stripe.Customer.list,
                email=email,
                limit=5
            )
            
            if not customers.data:
                logger.warning(f"No customers found for email: {email}", event_type="stripe_customer_not_found")
                return []
            
            transactions = []
            
            # Look up payment intents for each customer
            for customer in customers.data:
                # Get payment intents
                payment_intents = await asyncio.to_thread(
                    stripe.PaymentIntent.list,
                    customer=customer.id,
                    limit=10
                )
                
                for pi in payment_intents.data:
                    customer_email = None
                    
                    # Extract email from charge data if available
                    if pi.get('charges', {}).get('data'):
                        charge = pi['charges']['data'][0]
                        if charge.get('billing_details', {}).get('email'):
                            customer_email = charge['billing_details']['email']
                    
                    transactions.append({
                        "id": pi.id,
                        "object_type": "payment_intent",
                        "amount": Decimal(pi.amount) / 100,  # Convert cents to dollars
                        "customer_id": customer.id,
                        "customer_email": customer_email or email,
                        "created_at": datetime.fromtimestamp(pi.created, UTC)
                    })
                
                # Get subscriptions
                subscriptions = await asyncio.to_thread(
                    stripe.Subscription.list,
                    customer=customer.id,
                    limit=10
                )
                
                for sub in subscriptions.data:
                    transactions.append({
                        "id": sub.id,
                        "object_type": "subscription",
                        "customer_id": customer.id,
                        "customer_email": email,
                        "created_at": datetime.fromtimestamp(sub.created, UTC),
                        "subscription_data": {
                            "status": sub.status,
                            "current_period_start": datetime.fromtimestamp(sub.current_period_start, UTC),
                            "current_period_end": datetime.fromtimestamp(sub.current_period_end, UTC),
                            "items": sub.items.data
                        }
                    })
            
            # Sort transactions by created date (most recent first)
            transactions.sort(key=lambda x: x['created_at'], reverse=True)
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error finding transactions by email: {str(e)}", event_type="stripe_lookup_error", error=str(e))
            return []

    def _format_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format transaction data into a standardized structure.
        
        Args:
            transaction_data: Transaction data from Stripe
            
        Returns:
            Dict[str, Any]: Standardized transaction data
        """
        # Extract basic information that exists in all transaction types
        formatted_data = {
            "id": transaction_data.get("id"),
            "object_type": transaction_data.get("object_type"),
            "customer_id": transaction_data.get("customer_id"),
            "customer_email": transaction_data.get("customer_email"),
            "created_at": transaction_data.get("created_at")
        }
        
        # Add amount if present
        if "amount" in transaction_data:
            formatted_data["amount"] = transaction_data["amount"]
        
        # Add subscription data if present
        if "subscription_data" in transaction_data:
            formatted_data["subscription_data"] = transaction_data["subscription_data"]
        
        # Add subscription ID if present
        if "subscription_id" in transaction_data:
            formatted_data["subscription_id"] = transaction_data["subscription_id"]
        
        return formatted_data

    async def analyze_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze transaction data to determine type and attributes.
        
        Args:
            transaction_data: Transaction data from Stripe
            
        Returns:
            Dict[str, Any]: Analysis result
        """
        try:
            # Format transaction data
            transaction = self._format_transaction(transaction_data)
            
            # Initialize result
            result = {
                "transaction_type": "unknown",
                "recurring": False,
                "amount": Decimal('0.00'),
                "customer_id": transaction.get("customer_id"),
                "customer_email": transaction.get("customer_email"),
                "subscription_id": None,
                "plan_id": None,
                "product_id": None,
                "transaction_id": transaction.get("id"),
                "created_at": transaction.get("created_at") or datetime.now(UTC)
            }
            
            # Determine transaction type based on object type
            object_type = transaction.get("object_type")
            
            if object_type == "payment_intent":
                # One-time payment
                result["transaction_type"] = "oneoff"
                result["recurring"] = False
                result["amount"] = transaction.get("amount", Decimal('0.00'))
                
                # Try to get product information
                try:
                    payment_intent = await asyncio.to_thread(
                        stripe.PaymentIntent.retrieve,
                        transaction.get("id"),
                        expand=["metadata"]
                    )
                    
                    if payment_intent.get("metadata", {}).get("product_id"):
                        result["product_id"] = payment_intent["metadata"]["product_id"]
                except Exception as e:
                    logger.warning(f"Could not retrieve product info: {str(e)}", event_type="stripe_product_lookup_error")
            
            elif object_type == "subscription":
                # Subscription
                result["transaction_type"] = "subscription"
                result["recurring"] = True
                result["subscription_id"] = transaction.get("id")
                
                # Get subscription details to determine amount and plan
                subscription_data = transaction.get("subscription_data", {})
                
                if subscription_data and subscription_data.get("items"):
                    item = subscription_data["items"][0] if subscription_data["items"] else None
                    if item and item.get("plan"):
                        result["plan_id"] = item["plan"].get("id")
                        result["product_id"] = item["plan"].get("product")
                        
                        # Calculate amount
                        if item["plan"].get("amount"):
                            result["amount"] = Decimal(item["plan"]["amount"]) / 100
            
            elif object_type == "invoice":
                # Invoice (could be for subscription)
                subscription_id = transaction.get("subscription_id")
                
                if subscription_id:
                    # This is a subscription invoice
                    result["transaction_type"] = "subscription"
                    result["recurring"] = True
                    result["subscription_id"] = subscription_id
                    result["amount"] = transaction.get("amount", Decimal('0.00'))
                    
                    # Get subscription details
                    try:
                        subscription = await asyncio.to_thread(
                            stripe.Subscription.retrieve,
                            subscription_id
                        )
                        
                        if subscription and subscription.get("items", {}).get("data"):
                            item = subscription["items"]["data"][0]
                            if item and item.get("plan"):
                                result["plan_id"] = item["plan"].get("id")
                                result["product_id"] = item["plan"].get("product")
                    except Exception as e:
                        logger.warning(f"Could not retrieve subscription: {str(e)}", event_type="stripe_subscription_lookup_error")
                else:
                    # Regular invoice (one-time)
                    result["transaction_type"] = "oneoff"
                    result["amount"] = transaction.get("amount", Decimal('0.00'))
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing transaction: {str(e)}", event_type="stripe_analysis_error", error=str(e))
            raise

    async def handle_subscription_renewal(self, subscription_id: str) -> bool:
        """
        Handle subscription renewal event.
        
        Args:
            subscription_id: The Stripe subscription ID
            
        Returns:
            bool: True if renewal was processed, False otherwise
        """
        try:
            # Get subscription details
            subscription = await asyncio.to_thread(
                stripe.Subscription.retrieve,
                subscription_id
            )
            
            if not subscription:
                logger.warning(f"Subscription not found: {subscription_id}", event_type="stripe_subscription_not_found")
                return False
            
            logger.info(f"Processing subscription renewal: {subscription_id}", event_type="stripe_subscription_renewal")
            
            # Here we would typically update our local subscription record
            # and add credits to the user's account
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling subscription renewal: {str(e)}", event_type="stripe_renewal_error", error=str(e))
            return False

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """
        Cancel a Stripe subscription.
        
        Args:
            subscription_id: The Stripe subscription ID
            
        Returns:
            bool: True if cancellation was successful, False otherwise
        """
        try:
            # Cancel the subscription (at period end)
            result = await asyncio.to_thread(
                stripe.Subscription.modify,
                subscription_id,
                cancel_at_period_end=True
            )
            
            if result and result.get("cancel_at_period_end"):
                logger.info(f"Subscription scheduled for cancellation: {subscription_id}", event_type="stripe_subscription_cancellation")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling subscription: {str(e)}", event_type="stripe_cancellation_error", error=str(e))
            return False