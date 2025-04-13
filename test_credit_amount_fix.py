"""Test script to verify the credit amount fix."""

import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from fastapi import BackgroundTasks

from app.core.config import settings
from app.models.user import User
from app.services.credit.transaction import TransactionService
from app.log.logging import logger

async def test_credit_amount_fix():
    """Test that the credit amount from the frontend is correctly used."""
    print("\n=== Testing Credit Amount Fix ===\n")
    
    # Create async engine and session
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # 1. Create a test user
        # Generate a unique email with timestamp and UUID
        unique_email = f"test_user_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}@example.com"
        print(f"Creating test user with email: {unique_email}...")
        test_user = User(
            email=unique_email,
            hashed_password="hashed_password",
            is_verified=True,
            auth_type="password"
        )
        session.add(test_user)
        await session.commit()
        await session.refresh(test_user)
        print(f"Test user created with ID: {test_user.id}")
        
        # 2. Initialize the transaction service
        transaction_service = TransactionService()
        transaction_service.db = session
        
        # We need to set up the other services that TransactionService depends on
        from app.services.credit.base import BaseCreditService
        from app.services.credit.plan import PlanService
        from app.services.credit.stripe_integration import StripeIntegrationService
        
        base_service = BaseCreditService(session)
        
        plan_service = PlanService()
        plan_service.db = session
        
        stripe_service = StripeIntegrationService()
        stripe_service.db = session
        
        transaction_service.base_service = base_service
        transaction_service.plan_service = plan_service
        transaction_service.stripe_service = stripe_service
        
        # 3. Create a mock subscription ID
        mock_subscription_id = f"sub_test_{uuid.uuid4().hex[:16]}"
        
        # 4. Set the credit amount we want to test (300 credits)
        test_credit_amount = Decimal("300.00")
        print(f"\nTesting with credit amount: {test_credit_amount}")
        
        # 5. Mock the verify_transaction_id method to return a valid result
        original_verify_transaction_id = stripe_service.verify_transaction_id
        
        async def mock_verify_transaction_id(transaction_id):
            print(f"Mocking verification for transaction ID: {transaction_id}")
            return {
                "verified": True,
                "id": transaction_id,
                "object_type": "subscription",
                "amount": Decimal("79.00"),
                "customer_id": "cus_test",
                "status": "active",
                "plan_id": "price_test",
                "current_period_end": datetime.now(UTC)
            }
        
        stripe_service.verify_transaction_id = mock_verify_transaction_id
        
        # 6. Mock the check_active_subscription method to return None
        original_check_active_subscription = stripe_service.check_active_subscription
        
        async def mock_check_active_subscription(user_id):
            print(f"Mocking check_active_subscription for user ID: {user_id}")
            return None
        
        stripe_service.check_active_subscription = mock_check_active_subscription
        
        # 7. Mock the verify_subscription_active method to return True
        original_verify_subscription_active = stripe_service.verify_subscription_active
        
        async def mock_verify_subscription_active(subscription_id):
            print(f"Mocking verify_subscription_active for subscription ID: {subscription_id}")
            return True
        
        stripe_service.verify_subscription_active = mock_verify_subscription_active
        
        try:
            # 8. Process the subscription with our test credit amount
            print("\nProcessing subscription with test credit amount...")
            transaction, subscription = await transaction_service.verify_and_process_subscription(
                user_id=test_user.id,
                transaction_id=mock_subscription_id,
                background_tasks=BackgroundTasks(),
                amount=test_credit_amount
            )
            
            # 9. Verify the results
            print("\nVerifying results:")
            print(f"Transaction ID: {transaction.id}")
            print(f"Transaction Amount: {transaction.amount}")
            print(f"New Balance: {transaction.new_balance}")
            print(f"Subscription ID: {subscription.id}")
            print(f"Subscription Plan ID: {subscription.plan_id}")
            
            # 10. Check if the correct amount was added
            if transaction.amount == test_credit_amount:
                print("\n✅ SUCCESS: The correct credit amount was added!")
            else:
                print(f"\n❌ FAILURE: Wrong credit amount was added. Expected: {test_credit_amount}, Got: {transaction.amount}")
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            # Restore original methods
            stripe_service.verify_transaction_id = original_verify_transaction_id
            stripe_service.check_active_subscription = original_check_active_subscription
            stripe_service.verify_subscription_active = original_verify_subscription_active
            
            # Clean up test data
            print("\nCleaning up test data...")
            
            # Delete credit transactions
            from app.models.credit import CreditTransaction
            from sqlalchemy import text
            await session.execute(
                text("DELETE FROM credit_transactions WHERE user_id = :user_id"),
                {"user_id": test_user.id}
            )
            
            # Delete subscriptions
            await session.execute(
                text("DELETE FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": test_user.id}
            )
            
            # Delete user credit
            await session.execute(
                text("DELETE FROM user_credits WHERE user_id = :user_id"),
                {"user_id": test_user.id}
            )
            
            # Delete user
            await session.delete(test_user)
            await session.commit()
            
            print("Test data cleaned up successfully")

if __name__ == "__main__":
    asyncio.run(test_credit_amount_fix())