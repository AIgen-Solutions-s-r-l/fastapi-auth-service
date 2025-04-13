"""Test script to debug the Stripe items data access issue."""

import asyncio
import logging
import stripe
from app.core.config import settings

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def test_subscription_items_access():
    """Test accessing subscription items data."""
    print("\n=== Testing Stripe Subscription Items Access ===\n")
    
    # Configure Stripe API key
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    # Test subscription ID - use the one from the logs
    test_subscription_id = "sub_1RDQMxRwjs1KsbvtBkHPdFRk"
    
    print(f"Testing items access for subscription ID: {test_subscription_id}")
    
    try:
        # Retrieve the subscription directly
        subscription = await asyncio.to_thread(
            stripe.Subscription.retrieve,
            test_subscription_id
        )
        
        # Print subscription object type
        print(f"\nSubscription object type: {type(subscription)}")
        
        # Print subscription object representation
        print(f"\nSubscription object representation:")
        print(subscription)
        
        # Print items attribute
        print(f"\nItems attribute:")
        print(subscription.items)
        
        # Print items attribute type
        print(f"\nItems attribute type: {type(subscription.items)}")
        
        # Try to access items data
        print("\nTrying to access items data:")
        
        # Check if items has data attribute
        if hasattr(subscription.items, 'data'):
            print("subscription.items.data exists")
            print(subscription.items.data)
        else:
            print("subscription.items.data does not exist")
        
        # Try to access as dictionary
        if hasattr(subscription, 'to_dict'):
            sub_dict = subscription.to_dict()
            print("\nSubscription as dictionary:")
            if 'items' in sub_dict:
                print(f"items key exists in dictionary")
                print(f"items value: {sub_dict['items']}")
                
                if 'data' in sub_dict['items']:
                    print(f"data key exists in items")
                    print(f"data value: {sub_dict['items']['data']}")
        
        print("\nTest completed.")
        
    except Exception as e:
        print(f"Error during test: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_subscription_items_access())