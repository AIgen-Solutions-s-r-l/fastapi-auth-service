import asyncio
from datetime import datetime
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

async def test_one_time_payment_email_flow():
    """Test the complete flow from transaction processing to email sending for one-time payments."""
    logger.info("Starting one-time payment email flow test")
    
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
        transaction_id = f"pi_test_one_time_payment_{datetime.now().timestamp()}"
        
        # Mock the verify_transaction_id method to return a valid result
        original_verify = credit_service.transaction_service.stripe_service.verify_transaction_id
        
        async def mock_verify_transaction(*args, **kwargs):
            return {
                "verified": True,
                "id": transaction_id,
                "object_type": "payment_intent",
                "amount": Decimal("39.00"),
                "customer_id": "cus_test",
                "status": "succeeded"
            }
        
        # Replace with mock
        credit_service.transaction_service.stripe_service.verify_transaction_id = mock_verify_transaction
        
        try:
            # Process the one-time payment
            logger.info("Processing one-time payment")
            transaction = await credit_service.verify_and_process_one_time_payment(
                user_id=user.id,
                transaction_id=transaction_id,
                background_tasks=background_tasks,
                amount=Decimal("100.00")  # Credits to add
            )
            
            # Check if transaction was created
            if transaction:
                logger.info(f"Transaction created: ID {transaction.id}, Amount {transaction.amount}")
                
                # Check if email was queued
                logger.info(f"Background tasks: {len(background_tasks.tasks)} tasks")
                
                if background_tasks.tasks:
                    logger.info("Email was successfully queued")
                else:
                    logger.error("No email was queued")
            else:
                logger.error("Transaction was not created")
                
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
        finally:
            # Restore original method
            credit_service.transaction_service.stripe_service.verify_transaction_id = original_verify
        
        logger.info("Test completed")

if __name__ == "__main__":
    asyncio.run(test_one_time_payment_email_flow())