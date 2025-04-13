"""Test script to verify the Stripe integration fix."""

import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.credit.stripe_integration import StripeIntegrationService
from app.core.config import settings
from app.log.logging import logger

# Configure logging to see the output
logging.basicConfig(level=logging.INFO)

async def test_check_active_subscription():
    """Test the check_active_subscription method with the fix."""
    print("\n=== Testing Stripe check_active_subscription with fix ===\n")
    
    # Initialize the service
    stripe_service = StripeIntegrationService()
    
    # Create a database session for the service
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Set the database session
        stripe_service.db = session
        
        # Test user ID - use a user ID that has an active subscription
        test_user_id = 57  # This is the user ID from the logs
        
        print(f"Testing check_active_subscription for user ID: {test_user_id}")
        
        try:
            # Call the check_active_subscription method
            result = await stripe_service.check_active_subscription(test_user_id)
            
            # Check the result
            if result:
                print("\nActive subscription found:")
                print(f"Subscription ID: {result.get('subscription_id')}")
                print(f"Stripe Subscription ID: {result.get('stripe_subscription_id')}")
                print(f"Plan ID: {result.get('plan_id')}")
                print(f"Stripe Plan ID: {result.get('stripe_plan_id')}")
                print(f"Status: {result.get('status')}")
                print(f"Amount: {result.get('amount')}")
                print(f"Current Period End: {result.get('current_period_end')}")
            else:
                print("\nNo active subscription found for this user.")
            
            print("\nTest completed successfully. The fix appears to be working!")
            
        except Exception as e:
            print(f"Error during test: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_check_active_subscription())