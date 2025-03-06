"""
Test script to verify Stripe API connection using test mode keys.

This script will load the API keys from the .env file and use them to make 
basic Stripe API calls to verify connectivity.
"""

import asyncio
import os
import stripe
from datetime import datetime, UTC
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure Stripe with API key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe.api_version = os.getenv("STRIPE_API_VERSION", "2023-10-16")


async def test_list_customers():
    """Test listing customers from Stripe."""
    try:
        print("\n=== Testing Stripe Customer Listing ===")
        customers = await asyncio.to_thread(
            stripe.Customer.list,
            limit=5
        )
        
        print(f"Successfully retrieved {len(customers.data)} customers:")
        for customer in customers.data:
            print(f"- Customer ID: {customer.id}, Email: {customer.email}, Created: {datetime.fromtimestamp(customer.created, UTC)}")
        
        return True
    except Exception as e:
        print(f"Error listing customers: {str(e)}")
        return False


async def test_list_payment_methods():
    """Test listing payment methods from Stripe."""
    try:
        print("\n=== Testing Stripe Payment Methods Listing ===")
        payment_methods = await asyncio.to_thread(
            stripe.PaymentMethod.list,
            limit=5
        )
        
        print(f"Successfully retrieved {len(payment_methods.data)} payment methods:")
        for pm in payment_methods.data:
            print(f"- Payment Method ID: {pm.id}, Type: {pm.type}, Created: {datetime.fromtimestamp(pm.created, UTC)}")
        
        return True
    except Exception as e:
        print(f"Error listing payment methods: {str(e)}")
        return False


async def test_list_products():
    """Test listing products from Stripe."""
    try:
        print("\n=== Testing Stripe Product Listing ===")
        products = await asyncio.to_thread(
            stripe.Product.list,
            limit=5,
            active=True
        )
        
        print(f"Successfully retrieved {len(products.data)} products:")
        for product in products.data:
            print(f"- Product ID: {product.id}, Name: {product.name}, Active: {product.active}")
        
        return True
    except Exception as e:
        print(f"Error listing products: {str(e)}")
        return False


async def test_list_prices():
    """Test listing prices from Stripe."""
    try:
        print("\n=== Testing Stripe Price Listing ===")
        prices = await asyncio.to_thread(
            stripe.Price.list,
            limit=5,
            active=True
        )
        
        print(f"Successfully retrieved {len(prices.data)} prices:")
        for price in prices.data:
            amount = price.unit_amount / 100 if price.unit_amount else "N/A"
            print(f"- Price ID: {price.id}, Amount: ${amount}, Currency: {price.currency}, Product: {price.product}")
        
        return True
    except Exception as e:
        print(f"Error listing prices: {str(e)}")
        return False


async def test_payment_intents():
    """Test listing payment intents from Stripe."""
    try:
        print("\n=== Testing Stripe Payment Intent Listing ===")
        payment_intents = await asyncio.to_thread(
            stripe.PaymentIntent.list,
            limit=5
        )
        
        print(f"Successfully retrieved {len(payment_intents.data)} payment intents:")
        for pi in payment_intents.data:
            amount = pi.amount / 100 if pi.amount else "N/A"
            print(f"- Payment Intent ID: {pi.id}, Amount: ${amount}, Status: {pi.status}")
        
        return True
    except Exception as e:
        print(f"Error listing payment intents: {str(e)}")
        return False


async def test_subscriptions():
    """Test listing subscriptions from Stripe."""
    try:
        print("\n=== Testing Stripe Subscription Listing ===")
        subscriptions = await asyncio.to_thread(
            stripe.Subscription.list,
            limit=5
        )
        
        print(f"Successfully retrieved {len(subscriptions.data)} subscriptions:")
        for sub in subscriptions.data:
            print(f"- Subscription ID: {sub.id}, Status: {sub.status}, Customer: {sub.customer}")
        
        return True
    except Exception as e:
        print(f"Error listing subscriptions: {str(e)}")
        return False


async def create_test_customer():
    """Create a test customer in Stripe."""
    try:
        print("\n=== Creating Test Customer ===")
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            email="test_customer@example.com",
            name="Test Customer",
            description="Created by test script"
        )
        
        print(f"Successfully created test customer:")
        print(f"- Customer ID: {customer.id}")
        print(f"- Email: {customer.email}")
        print(f"- Name: {customer.name}")
        print(f"- Created: {datetime.fromtimestamp(customer.created, UTC)}")
        
        return customer
    except Exception as e:
        print(f"Error creating test customer: {str(e)}")
        return None


async def main():
    """Main function to test Stripe API connectivity."""
    print("=== Stripe API Test ===")
    print(f"API Version: {stripe.api_version}")
    print(f"API Key (first 8 chars): {stripe.api_key[:8]}...")
    
    # Test API connectivity
    tests = [
        test_list_customers,
        test_list_payment_methods,
        test_list_products,
        test_list_prices,
        test_payment_intents,
        test_subscriptions
    ]
    
    results = []
    for test in tests:
        results.append(await test())
    
    # Print summary
    print("\n=== Test Summary ===")
    success_count = results.count(True)
    print(f"Successful tests: {success_count}/{len(tests)}")
    
    if all(results):
        print("\n✅ All Stripe API tests passed! Connection is working.")
    else:
        print("\n❌ Some Stripe API tests failed. Check the error messages above.")
    
    # Create a test customer if all tests are successful
    if all(results):
        print("\nWould you like to create a test customer? (y/n)")
        response = input()
        if response.lower() == 'y':
            await create_test_customer()


if __name__ == "__main__":
    asyncio.run(main())