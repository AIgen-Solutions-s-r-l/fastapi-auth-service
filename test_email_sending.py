import asyncio
from decimal import Decimal
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.user import User
from app.services.credit.transaction import TransactionService
from app.services.email_service import EmailService
from app.log.logging import logger

# Create a test database engine
engine = create_async_engine(settings.database_url)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def test_one_time_purchase_email():
    """Test if emails are sent for one-time purchases."""
    logger.info("Starting one-time purchase email test")
    
    # Create a session
    async with async_session() as session:
        # Get a test user
        user = await session.get(User, 1)  # Assuming user ID 1 exists
        if not user:
            logger.error("Test user not found")
            return
        
        # Create background tasks
        background_tasks = BackgroundTasks()
        
        # Test direct email service
        logger.info("Testing direct email service")
        email_service = EmailService(background_tasks, session)
        await email_service.send_one_time_credit_purchase(
            user=user,
            amount=Decimal("39.00"),
            credits=Decimal("100.00")
        )
        
        # Log what's in the background tasks
        logger.info(f"Background tasks after direct email: {background_tasks.tasks}")
        
        # Test transaction service
        logger.info("Testing transaction service")
        transaction_service = TransactionService()
        transaction_service.db = session
        
        # Call the _send_email_notification method
        await transaction_service._send_email_notification(
            background_tasks=background_tasks,
            user_id=user.id,
            plan=None,
            subscription=None,
            email_type="one_time_purchase",
            amount=Decimal("39.00"),
            credit_amount=Decimal("100.00")
        )
        
        # Log what's in the background tasks
        logger.info(f"Background tasks after transaction service: {background_tasks.tasks}")
        
        logger.info("Test completed")

if __name__ == "__main__":
    asyncio.run(test_one_time_purchase_email())