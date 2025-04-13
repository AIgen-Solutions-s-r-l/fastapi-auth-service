"""Test script for Stripe subscription verification."""

import asyncio
import logging
from app.services.credit.stripe_integration import StripeIntegrationService
from app.log.logging import logger

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def test_subscription_verification():
    """Test the subscription verification process."""
    print("\n=== Testing Stripe Subscription Verification ===\n")
    
    # Initialize the service
    stripe_service = StripeIntegrationService()
    
    # Test subscription ID - use the one from the logs
    test_subscription_id = "sub_1RDPpVRwjs1KsbvtgzrFfGdR"
    
    print(f"Testing verification for subscription ID: {test_subscription_id}")
    
    try:
        # Call the verify_transaction_id method
        result = await stripe_service.verify_transaction_id(test_subscription_id)
        
        # Check the result
        print("\nVerification Result:")
        print(f"Verified: {result.get('verified', False)}")
        
        # Print all keys in the result for debugging
        print("\nAll result keys:")
        for key, value in result.items():
            print(f"{key}: {value}")
        
        # If we get here without seeing the "Transaction ID not verified" warning,
        # then our fix worked correctly
        print("\nTest completed successfully. Check the logs to ensure there are no contradictory messages.")
        print("You should see 'Transaction verified as Subscription' but NOT 'Transaction ID not verified'")
        
    except Exception as e:
        print(f"Error during test: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_subscription_verification())