"""
Example script demonstrating the use of the Stripe integration with the credits system.

This script shows how to:
1. Process a one-time purchase from Stripe
2. Process a subscription from Stripe
3. Simulate webhook events for testing

Note: This script is for demonstration purposes only and should be adapted to your specific needs.
"""

import asyncio
import json
import hmac
import hashlib
import time
from datetime import datetime, UTC
from decimal import Decimal

import httpx
import stripe
from fastapi import FastAPI, BackgroundTasks, Request
from pydantic import BaseModel


# Mock API URL
API_BASE_URL = "http://localhost:8000"

# Stripe configuration
STRIPE_SECRET_KEY = "sk_test_example"
STRIPE_WEBHOOK_SECRET = "whsec_REMOVED"
STRIPE_API_VERSION = "2023-10-16"

# Configure Stripe
stripe.api_key = STRIPE_SECRET_KEY
stripe.api_version = STRIPE_API_VERSION


class User:
    """Mock user class for the example."""
    
    def __init__(self, id, email, stripe_customer_id=None):
        self.id = id
        self.email = email
        self.stripe_customer_id = stripe_customer_id


# Example user
example_user = User(
    id=1,
    email="customer@example.com",
    stripe_customer_id="cus_1234567890"
)


async def create_payment_intent(amount: float, user: User):
    """
    Create a payment intent in Stripe.
    
    Args:
        amount: Amount in dollars
        user: User to create payment for
        
    Returns:
        Payment intent object
    """
    try:
        # Create a payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency="usd",
            customer=user.stripe_customer_id,
            metadata={
                "user_id": str(user.id),
                "product_id": "prod_oneoff_credits"
            }
        )
        
        print(f"Created payment intent: {payment_intent.id}")
        return payment_intent
    except Exception as e:
        print(f"Error creating payment intent: {str(e)}")
        return None


async def create_subscription(user: User, plan_id: str):
    """
    Create a subscription in Stripe.
    
    Args:
        user: User to create subscription for
        plan_id: Stripe price ID for the plan
        
    Returns:
        Subscription object
    """
    try:
        # Create a subscription
        subscription = stripe.Subscription.create(
            customer=user.stripe_customer_id,
            items=[
                {"price": plan_id}
            ],
            metadata={
                "user_id": str(user.id)
            }
        )
        
        print(f"Created subscription: {subscription.id}")
        return subscription
    except Exception as e:
        print(f"Error creating subscription: {str(e)}")
        return None


async def process_one_time_purchase_example():
    """Example of processing a one-time purchase from Stripe."""
    print("\n=== Processing One-Time Purchase Example ===")
    
    # 1. Create a payment intent in Stripe
    payment_intent = await create_payment_intent(29.99, example_user)
    if not payment_intent:
        return
    
    # 2. Simulate successful payment (in a real scenario, this happens in the frontend)
    payment_intent_id = payment_intent.id
    
    # 3. Process the payment intent through our API
    async with httpx.AsyncClient() as client:
        # Get auth token (simplified for example)
        token = "example_auth_token"
        
        # Call the API to add credits from the payment intent
        response = await client.post(
            f"{API_BASE_URL}/credits/stripe/add",
            json={
                "transaction_id": payment_intent_id,
                "transaction_type": "oneoff"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"Successfully processed one-time purchase:")
            print(f"- Transaction ID: {result['transaction']['transaction_id']}")
            print(f"- Amount: ${result['transaction']['amount']}")
            print(f"- Credits Added: {result['transaction']['amount'] * 10}")
            print(f"- New Balance: {result['new_balance']}")
        else:
            print(f"Error processing one-time purchase: {response.text}")


async def process_subscription_example():
    """Example of processing a subscription from Stripe."""
    print("\n=== Processing Subscription Example ===")
    
    # 1. Create a subscription in Stripe
    # Use an example plan price ID (replace with your actual price ID)
    price_id = "price_1234567890"
    subscription = await create_subscription(example_user, price_id)
    if not subscription:
        return
    
    # 2. Process the subscription through our API
    async with httpx.AsyncClient() as client:
        # Get auth token (simplified for example)
        token = "example_auth_token"
        
        # Call the API to add credits from the subscription
        response = await client.post(
            f"{API_BASE_URL}/credits/stripe/add",
            json={
                "transaction_id": subscription.id,
                "transaction_type": "subscription"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"Successfully processed subscription:")
            print(f"- Subscription ID: {result['transaction']['subscription_id']}")
            print(f"- Plan ID: {result['transaction']['plan_id']}")
            print(f"- Amount: ${result['transaction']['amount']}")
            print(f"- Credits Added: {result['transaction']['amount'] * 10}")
            print(f"- New Balance: {result['new_balance']}")
        else:
            print(f"Error processing subscription: {response.text}")


def generate_webhook_signature(payload, secret, timestamp=None):
    """
    Generate a Stripe webhook signature for testing.
    
    Args:
        payload: The JSON payload as a string
        secret: The webhook secret key
        timestamp: Optional timestamp (defaults to current time)
        
    Returns:
        A valid Stripe signature string
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    # Create the signed_payload string
    signed_payload = f"{timestamp}.{payload}"
    
    # Create the signature
    signature = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Format the signature as Stripe expects
    return f"t={timestamp},v1={signature}"


async def simulate_webhook_event(event_type, event_data):
    """
    Simulate sending a webhook event to our API.
    
    Args:
        event_type: The type of event (e.g., "invoice.payment_succeeded")
        event_data: The event data
        
    Returns:
        API response
    """
    # Create the event payload
    event = {
        "id": f"evt_{int(time.time())}",
        "object": "event",
        "api_version": STRIPE_API_VERSION,
        "created": int(time.time()),
        "data": {
            "object": event_data
        },
        "type": event_type
    }
    
    # Convert to JSON
    payload = json.dumps(event)
    
    # Generate signature
    signature = generate_webhook_signature(payload, STRIPE_WEBHOOK_SECRET)
    
    # Send the webhook event
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_BASE_URL}/webhook/stripe",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": signature
            }
        )
        
        return response


async def webhook_examples():
    """Examples of simulating webhook events."""
    print("\n=== Webhook Event Examples ===")
    
    # Example 1: Simulate a payment_intent.succeeded webhook event
    print("\n1. Simulating payment_intent.succeeded event")
    payment_intent_data = {
        "id": "pi_1234567890",
        "object": "payment_intent",
        "amount": 2999,  # $29.99
        "currency": "usd",
        "customer": "cus_1234567890",
        "metadata": {
            "product_id": "prod_oneoff_credits"
        },
        "charges": {
            "data": [
                {
                    "id": "ch_1234567890",
                    "billing_details": {
                        "email": "customer@example.com"
                    }
                }
            ]
        }
    }
    
    response = await simulate_webhook_event("payment_intent.succeeded", payment_intent_data)
    if response.status_code == 200:
        result = response.json()
        print(f"Successfully processed webhook event:")
        print(f"- Event Type: {result['event_type']}")
        print(f"- Processed: {result['processed']}")
        print(f"- Result: {result.get('result', {})}")
    else:
        print(f"Error processing webhook event: {response.text}")
    
    # Example 2: Simulate an invoice.payment_succeeded webhook event
    print("\n2. Simulating invoice.payment_succeeded event")
    invoice_data = {
        "id": "in_1234567890",
        "object": "invoice",
        "amount_paid": 4999,  # $49.99
        "currency": "usd",
        "customer": "cus_1234567890",
        "customer_email": "customer@example.com",
        "subscription": "sub_1234567890",
        "status": "paid",
        "lines": {
            "data": [
                {
                    "id": "il_1234567890",
                    "object": "line_item",
                    "amount": 4999,
                    "currency": "usd",
                    "plan": {
                        "id": "price_1234567890",
                        "product": "prod_1234567890"
                    }
                }
            ]
        }
    }
    
    response = await simulate_webhook_event("invoice.payment_succeeded", invoice_data)
    if response.status_code == 200:
        result = response.json()
        print(f"Successfully processed webhook event:")
        print(f"- Event Type: {result['event_type']}")
        print(f"- Processed: {result['processed']}")
        print(f"- Result: {result.get('result', {})}")
    else:
        print(f"Error processing webhook event: {response.text}")
    
    # Example 3: Simulate a customer.subscription.updated webhook event
    print("\n3. Simulating customer.subscription.updated event")
    subscription_data = {
        "id": "sub_1234567890",
        "object": "subscription",
        "customer": "cus_1234567890",
        "status": "active",
        "current_period_start": int(time.time()),
        "current_period_end": int(time.time()) + 2592000,  # +30 days
        "items": {
            "data": [
                {
                    "id": "si_1234567890",
                    "plan": {
                        "id": "price_1234567890",
                        "product": "prod_1234567890",
                        "amount": 4999,
                        "currency": "usd"
                    }
                }
            ]
        }
    }
    
    response = await simulate_webhook_event("customer.subscription.updated", subscription_data)
    if response.status_code == 200:
        result = response.json()
        print(f"Successfully processed webhook event:")
        print(f"- Event Type: {result['event_type']}")
        print(f"- Processed: {result['processed']}")
        print(f"- Result: {result.get('result', {})}")
    else:
        print(f"Error processing webhook event: {response.text}")


async def main():
    """Main function to run examples."""
    print("=== Stripe Credits Integration Examples ===")
    
    # Note: In a real application, you would run these examples with your actual API
    # and Stripe configuration. This example uses mock data for demonstration purposes.
    
    # Uncomment the examples you want to run:
    
    # Process a one-time purchase
    # await process_one_time_purchase_example()
    
    # Process a subscription
    # await process_subscription_example()
    
    # Simulate webhook events
    # await webhook_examples()
    
    print("\nExamples completed. Uncomment the desired examples in the main() function to run them.")


if __name__ == "__main__":
    asyncio.run(main())