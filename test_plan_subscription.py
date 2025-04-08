"""Test script to verify plan and subscription functionality after tier removal."""

import asyncio
import sys
import uuid
from decimal import Decimal
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from app.core.config import settings
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.services.credit_service import CreditService

async def test_plan_functionality():
    """Test plan creation, retrieval, and update functionality."""
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
        
        # 2. Create a test plan
        print("\nCreating test plan...")
        test_plan = Plan(
            name="Test Plan",
            credit_amount=Decimal("100.00"),
            price=Decimal("9.99"),
            is_active=True,
            description="Test plan created after tier removal"
        )
        session.add(test_plan)
        await session.commit()
        await session.refresh(test_plan)
        print(f"Test plan created with ID: {test_plan.id}")
        print(f"Plan details: {test_plan.name}, Credits: {test_plan.credit_amount}, Price: {test_plan.price}")
        
        # 3. Retrieve the plan
        print("\nRetrieving test plan...")
        retrieved_plan = await session.get(Plan, test_plan.id)
        if retrieved_plan:
            print(f"Successfully retrieved plan: {retrieved_plan.name}")
            print(f"Plan details: Credits: {retrieved_plan.credit_amount}, Price: {retrieved_plan.price}")
        else:
            print("Failed to retrieve plan")
            return False
        
        # 4. Update the plan
        print("\nUpdating test plan...")
        retrieved_plan.credit_amount = Decimal("150.00")
        retrieved_plan.price = Decimal("14.99")
        retrieved_plan.description = "Updated test plan"
        await session.commit()
        await session.refresh(retrieved_plan)
        print(f"Updated plan details: {retrieved_plan.name}, Credits: {retrieved_plan.credit_amount}, Price: {retrieved_plan.price}")
        
        # 5. Create a second plan for subscription upgrade test
        print("\nCreating premium plan...")
        premium_plan = Plan(
            name="Premium Plan",
            credit_amount=Decimal("300.00"),
            price=Decimal("29.99"),
            is_active=True,
            description="Premium plan for upgrade testing"
        )
        session.add(premium_plan)
        await session.commit()
        await session.refresh(premium_plan)
        print(f"Premium plan created with ID: {premium_plan.id}")
        
        # 6. Create a subscription
        print("\nCreating subscription...")
        credit_service = CreditService(session)
        
        # Calculate renewal date
        start_date = datetime.now(UTC)
        renewal_date = await credit_service.calculate_renewal_date(start_date)
        
        subscription = Subscription(
            user_id=test_user.id,
            plan_id=test_plan.id,
            start_date=start_date,
            renewal_date=renewal_date,
            is_active=True,
            auto_renew=True
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        print(f"Subscription created with ID: {subscription.id}")
        print(f"Subscription details: User ID: {subscription.user_id}, Plan ID: {subscription.plan_id}")
        print(f"Start date: {subscription.start_date}, Renewal date: {subscription.renewal_date}")
        
        # 7. Add credits to user
        print("\nAdding credits to user...")
        transaction = await credit_service.add_credits(
            user_id=test_user.id,
            amount=test_plan.credit_amount,
            description=f"Credits from {test_plan.name} subscription",
            plan_id=test_plan.id,
            subscription_id=subscription.id
        )
        print(f"Added {transaction.amount} credits to user {test_user.id}")
        print(f"New balance: {transaction.new_balance}")
        
        # 8. Upgrade subscription
        print("\nUpgrading subscription...")
        # Deactivate current subscription
        subscription.is_active = False
        await session.commit()
        
        # Create new subscription with premium plan
        new_subscription = Subscription(
            user_id=test_user.id,
            plan_id=premium_plan.id,
            start_date=datetime.now(UTC),
            renewal_date=await credit_service.calculate_renewal_date(datetime.now(UTC)),
            is_active=True,
            auto_renew=True
        )
        session.add(new_subscription)
        await session.commit()
        await session.refresh(new_subscription)
        print(f"New subscription created with ID: {new_subscription.id}")
        print(f"New subscription details: User ID: {new_subscription.user_id}, Plan ID: {new_subscription.plan_id}")
        
        # 9. Add credits for the upgraded plan
        print("\nAdding credits for upgraded plan...")
        upgrade_transaction = await credit_service.add_credits(
            user_id=test_user.id,
            amount=premium_plan.credit_amount,
            description=f"Credits from {premium_plan.name} subscription upgrade",
            plan_id=premium_plan.id,
            subscription_id=new_subscription.id
        )
        print(f"Added {upgrade_transaction.amount} credits to user {test_user.id}")
        print(f"New balance: {upgrade_transaction.new_balance}")
        
        # 10. Clean up test data
        print("\nCleaning up test data...")
        
        # First, delete credit transactions that reference subscriptions
        from app.models.credit import CreditTransaction
        
        # Get all credit transactions for this user
        result = await session.execute(
            text("SELECT id FROM credit_transactions WHERE user_id = :user_id"),
            {"user_id": test_user.id}
        )
        transaction_ids = result.scalars().all()
        
        # Delete credit transactions
        if transaction_ids:
            print(f"Deleting {len(transaction_ids)} credit transactions...")
            await session.execute(
                text("DELETE FROM credit_transactions WHERE id = :id"),
                [{"id": tx_id} for tx_id in transaction_ids]
            )
            await session.commit()
        
        # Now delete subscriptions
        print("Deleting subscriptions...")
        await session.execute(
            text("DELETE FROM subscriptions WHERE user_id = :user_id"),
            {"user_id": test_user.id}
        )
        await session.commit()
        
        # Delete plans
        print("Deleting plans...")
        await session.delete(test_plan)
        await session.delete(premium_plan)
        await session.commit()
        
        # Delete user credit
        print("Deleting user credit...")
        await session.execute(
            text("DELETE FROM user_credits WHERE user_id = :user_id"),
            {"user_id": test_user.id}
        )
        await session.commit()
        
        # Delete user
        print("Deleting user...")
        await session.delete(test_user)
        await session.commit()
        
        print("Test data cleaned up successfully")
        
        print("\nAll tests completed successfully!")
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_plan_functionality())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        sys.exit(1)