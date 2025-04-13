import asyncio
from datetime import datetime, UTC
from decimal import Decimal
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user import User
from app.services.credit.transaction import TransactionService
from app.services.credit_service import CreditService
from app.log.logging import logger

# Create a test database engine
engine = create_async_engine(settings.database_url)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def test_subscription_email_double_sending():
    """Test if emails are double-sent for subscriptions."""
    logger.info("Starting test to verify if subscription emails are double-sent")
    
    # Create a session
    async with async_session() as session:
        # Get a test user
        user = await session.get(User, 1)  # Assuming user ID 1 exists
        if not user:
            logger.error("Test user not found")
            return
        
        # Create background tasks
        background_tasks = BackgroundTasks()
        
        # Initialize credit service
        credit_service = CreditService(session)
        
        # Create a mock transaction ID
        transaction_id = f"sub_test_subscription_{datetime.now(UTC).timestamp()}"
        
        # Mock the verify_transaction_id method to return a valid result
        original_verify = credit_service.transaction_service.stripe_service.verify_transaction_id
        original_verify_active = credit_service.transaction_service.stripe_service.verify_subscription_active
        
        async def mock_verify_transaction(*args, **kwargs):
            return {
                "verified": True,
                "id": transaction_id,
                "object_type": "subscription",
                "amount": Decimal("39.00"),
                "customer_id": "cus_test",
                "status": "active",
                "plan_id": "price_test",
                "plan_name": "Test Plan"
            }
        
        async def mock_verify_subscription_active(*args, **kwargs):
            return True
        
        # Replace with mocks
        credit_service.transaction_service.stripe_service.verify_transaction_id = mock_verify_transaction
        credit_service.transaction_service.stripe_service.verify_subscription_active = mock_verify_subscription_active
        
        # Mock the check_active_subscription method to return None (no active subscription)
        original_check_active = credit_service.transaction_service.stripe_service.check_active_subscription
        
        async def mock_check_active_subscription(*args, **kwargs):
            return None
        
        credit_service.transaction_service.stripe_service.check_active_subscription = mock_check_active_subscription
        
        # Mock the _find_matching_plan method to return a valid plan ID
        original_find_plan = credit_service.transaction_service._find_matching_plan
        
        async def mock_find_matching_plan(*args, **kwargs):
            return 1  # Return a valid plan ID
        
        credit_service.transaction_service._find_matching_plan = mock_find_matching_plan
        
        try:
            # Process the subscription
            logger.info("Processing subscription")
            transaction, subscription = await credit_service.verify_and_process_subscription(
                user_id=user.id,
                transaction_id=transaction_id,
                background_tasks=background_tasks,
                amount=Decimal("100.00")  # Credits to add
            )
            
            # Check if transaction and subscription were created
            if transaction and subscription:
                logger.info(f"Transaction created: ID {transaction.id}, Amount {transaction.amount}")
                logger.info(f"Subscription created: ID {subscription.id}, Plan ID {subscription.plan_id}")
                
                # Check how many email tasks were queued
                email_tasks_count = len(background_tasks.tasks)
                logger.info(f"Background tasks: {email_tasks_count} tasks")
                
                if email_tasks_count == 1:
                    logger.info("✅ Test passed: Exactly one email was queued")
                elif email_tasks_count == 0:
                    logger.error("❌ Test failed: No email was queued")
                else:
                    logger.error(f"❌ Test failed: {email_tasks_count} emails were queued (expected 1)")
            else:
                logger.error("Transaction or subscription was not created")
                
        except Exception as e:
            logger.error(f"Error processing subscription: {str(e)}")
        finally:
            # Restore original methods
            credit_service.transaction_service.stripe_service.verify_transaction_id = original_verify
            credit_service.transaction_service.stripe_service.verify_subscription_active = original_verify_active
            credit_service.transaction_service.stripe_service.check_active_subscription = original_check_active
            credit_service.transaction_service._find_matching_plan = original_find_plan
        
        logger.info("Test completed")

if __name__ == "__main__":
    asyncio.run(test_subscription_email_double_sending())