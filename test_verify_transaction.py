"""Test script to verify the Stripe transaction verification fix."""

import asyncio
import logging
from app.services.credit.stripe_integration import StripeIntegrationService
from app.log.logging import logger

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def test_verify_transaction_id():
    """Test the verify_transaction_id method with the fix."""
    print("\n=== Testing Stripe verify_transaction_id with fix ===\n")
    
    # Initialize the service
    stripe_service = StripeIntegrationService()
    
    # Test subscription ID - use the one from the logs
    test_subscription_id = "sub_1RDQOURwjs1KsbvtE7GFGZru"
    
    print(f"Testing verify_transaction_id for subscription ID: {test_subscription_id}")
    
    try:
        # Call the verify_transaction_id method
        result = await stripe_service.verify_transaction_id(test_subscription_id)
        
        # Check the result
        print("\nVerification Result:")
        print(f"Verified: {result.get('verified', False)}")
        print(f"ID: {result.get('id')}")
        print(f"Object Type: {result.get('object_type')}")
        
        # Print amount and plan_id if available
        if 'amount' in result:
            print(f"Amount: {result.get('amount')}")
        if 'plan_id' in result:
            print(f"Plan ID: {result.get('plan_id')}")
        if 'customer_id' in result:
            print(f"Customer ID: {result.get('customer_id')}")
        if 'status' in result:
            print(f"Status: {result.get('status')}")
        if 'current_period_end' in result:
            print(f"Current Period End: {result.get('current_period_end')}")
        
        # Print all keys in the result for debugging
        print("\nAll result keys:")
        for key, value in result.items():
            print(f"{key}: {value}")
        
        print("\nTest completed successfully. The fix appears to be working!")
        
    except Exception as e:
        print(f"Error during test: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_verify_transaction_id())