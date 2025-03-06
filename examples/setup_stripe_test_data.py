"""
Script to set up test data in Stripe for our credit system integration.

This script will:
1. Create test products representing credit packages
2. Create prices for those products
3. Set up metadata for the integration

This gives us data to work with when testing the credit system integration.
"""

import asyncio
import os
import stripe
import json
from datetime import datetime, UTC
from dotenv import load_dotenv
from decimal import Decimal

# Load environment variables from .env file
load_dotenv()

# Configure Stripe with API key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe.api_version = os.getenv("STRIPE_API_VERSION", "2023-10-16")

# Our test customer ID from previous script
TEST_CUSTOMER_ID = "cus_RrcXo9SJ5hwuzG"


async def create_credit_product():
    """Create a product for credits in Stripe."""
    try:
        print("\n=== Creating Credit Product ===")
        product = await asyncio.to_thread(
            stripe.Product.create,
            name="Credit Package",
            description="Credits for our service",
            metadata={
                "product_type": "credits",
                "is_subscription": "false"
            }
        )
        
        print(f"Successfully created product:")
        print(f"- Product ID: {product.id}")
        print(f"- Name: {product.name}")
        print(f"- Description: {product.description}")
        
        return product
    except Exception as e:
        print(f"Error creating product: {str(e)}")
        return None


async def create_subscription_product():
    """Create a product for credit subscriptions in Stripe."""
    try:
        print("\n=== Creating Subscription Product ===")
        product = await asyncio.to_thread(
            stripe.Product.create,
            name="Credit Subscription",
            description="Monthly credit subscription",
            metadata={
                "product_type": "credits",
                "is_subscription": "true"
            }
        )
        
        print(f"Successfully created subscription product:")
        print(f"- Product ID: {product.id}")
        print(f"- Name: {product.name}")
        print(f"- Description: {product.description}")
        
        return product
    except Exception as e:
        print(f"Error creating subscription product: {str(e)}")
        return None


async def create_prices(one_time_product_id, subscription_product_id):
    """Create prices for the credit products."""
    prices = []
    
    try:
        # Create one-time prices
        print("\n=== Creating One-time Credit Prices ===")
        price_tiers = [
            {"amount": 1999, "credits": 200},  # $19.99 for 200 credits
            {"amount": 4999, "credits": 600},  # $49.99 for 600 credits
            {"amount": 9999, "credits": 1500}  # $99.99 for 1500 credits
        ]
        
        for tier in price_tiers:
            price = await asyncio.to_thread(
                stripe.Price.create,
                product=one_time_product_id,
                unit_amount=tier["amount"],
                currency="usd",
                metadata={
                    "credits": str(tier["credits"]),
                    "price_type": "one_time"
                }
            )
            
            print(f"Created one-time price: ${tier['amount']/100} for {tier['credits']} credits (ID: {price.id})")
            prices.append(price)
        
        # Create subscription prices
        print("\n=== Creating Subscription Credit Prices ===")
        subscription_tiers = [
            {"amount": 999, "credits": 100},    # $9.99/month for 100 credits
            {"amount": 2499, "credits": 300},   # $24.99/month for 300 credits
            {"amount": 4999, "credits": 700}    # $49.99/month for 700 credits
        ]
        
        for tier in subscription_tiers:
            price = await asyncio.to_thread(
                stripe.Price.create,
                product=subscription_product_id,
                unit_amount=tier["amount"],
                currency="usd",
                recurring={"interval": "month"},
                metadata={
                    "credits": str(tier["credits"]),
                    "price_type": "subscription"
                }
            )
            
            print(f"Created subscription price: ${tier['amount']/100}/month for {tier['credits']} credits (ID: {price.id})")
            prices.append(price)
        
        return prices
    except Exception as e:
        print(f"Error creating prices: {str(e)}")
        return []


async def create_test_payment_intent(price_id, amount):
    """Create a test payment intent for a one-time purchase."""
    try:
        print(f"\n=== Creating Test Payment Intent ===")
        payment_intent = await asyncio.to_thread(
            stripe.PaymentIntent.create,
            amount=amount,
            currency="usd",
            customer=TEST_CUSTOMER_ID,
            metadata={
                "price_id": price_id,
                "product_type": "credits"
            }
        )
        
        print(f"Successfully created payment intent:")
        print(f"- Payment Intent ID: {payment_intent.id}")
        print(f"- Amount: ${payment_intent.amount/100}")
        print(f"- Status: {payment_intent.status}")
        print(f"- Customer: {payment_intent.customer}")
        
        return payment_intent
    except Exception as e:
        print(f"Error creating payment intent: {str(e)}")
        return None


async def create_test_subscription(price_id):
    """Create a test subscription."""
    try:
        print(f"\n=== Creating Test Subscription ===")
        subscription = await asyncio.to_thread(
            stripe.Subscription.create,
            customer=TEST_CUSTOMER_ID,
            items=[
                {"price": price_id}
            ],
            metadata={
                "product_type": "credits"
            }
        )
        
        print(f"Successfully created subscription:")
        print(f"- Subscription ID: {subscription.id}")
        print(f"- Status: {subscription.status}")
        print(f"- Customer: {subscription.customer}")
        
        # Print items
        for item in subscription.items.data:
            print(f"- Item: {item.price.id} (${item.price.unit_amount/100})")
        
        return subscription
    except Exception as e:
        print(f"Error creating subscription: {str(e)}")
        return None


async def save_test_data(data):
    """Save test data to a JSON file for later use."""
    filename = "stripe_test_data.json"
    
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\nTest data saved to {filename}")
    except Exception as e:
        print(f"Error saving test data: {str(e)}")


async def main():
    """Main function to set up Stripe test data."""
    print("=== Setting Up Stripe Test Data ===")
    
    # Store all our created test data
    test_data = {
        "created_at": datetime.now(UTC).isoformat(),
        "customer_id": TEST_CUSTOMER_ID,
        "products": {},
        "prices": [],
        "payment_intents": [],
        "subscriptions": []
    }
    
    # Create products
    one_time_product = await create_credit_product()
    subscription_product = await create_subscription_product()
    
    if one_time_product:
        test_data["products"]["one_time"] = {
            "id": one_time_product.id,
            "name": one_time_product.name
        }
    
    if subscription_product:
        test_data["products"]["subscription"] = {
            "id": subscription_product.id,
            "name": subscription_product.name
        }
    
    # Create prices if we have products
    if one_time_product and subscription_product:
        prices = await create_prices(one_time_product.id, subscription_product.id)
        
        # Store price data
        for price in prices:
            price_data = {
                "id": price.id,
                "product_id": price.product,
                "amount": price.unit_amount,
                "currency": price.currency,
                "type": price.metadata.get("price_type", "unknown"),
                "credits": int(price.metadata.get("credits", 0))
            }
            test_data["prices"].append(price_data)
        
        # Create a test payment intent for the first one-time price
        one_time_prices = [p for p in prices if p.metadata.get("price_type") == "one_time"]
        if one_time_prices:
            price = one_time_prices[0]
            payment_intent = await create_test_payment_intent(price.id, price.unit_amount)
            if payment_intent:
                test_data["payment_intents"].append({
                    "id": payment_intent.id,
                    "amount": payment_intent.amount,
                    "price_id": price.id
                })
        
        # Create a test subscription for the first subscription price
        subscription_prices = [p for p in prices if p.metadata.get("price_type") == "subscription"]
        if subscription_prices:
            price = subscription_prices[0]
            subscription = await create_test_subscription(price.id)
            if subscription:
                test_data["subscriptions"].append({
                    "id": subscription.id,
                    "price_id": price.id,
                    "status": subscription.status
                })
    
    # Save all test data to a file
    await save_test_data(test_data)
    
    print("\n=== Test Data Setup Complete ===")
    print(f"- Products created: {len(test_data['products'])}")
    print(f"- Prices created: {len(test_data['prices'])}")
    print(f"- Payment intents created: {len(test_data['payment_intents'])}")
    print(f"- Subscriptions created: {len(test_data['subscriptions'])}")
    print("\nYou can use this test data to verify the credit system integration.")
    print("The test data has been saved to 'stripe_test_data.json' for reference.")


if __name__ == "__main__":
    asyncio.run(main())