"""
Script to prepare the test environment for Stripe integration.

This script will:
1. Add test plans to the database that match our Stripe prices
2. Create a test user with the Stripe customer ID
3. Set up the necessary environment for testing the credit system integration
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Add the current directory to the path so we can import app modules
sys.path.append(os.getcwd())

from app.models.user import User
from app.models.plan import Plan, PlanTier
from app.models.credit import UserCredit
from app.core.config import settings
from app.core.security import get_password_hash

# Load environment variables and Stripe test data
load_dotenv()
with open('stripe_test_data.json', 'r') as f:
    STRIPE_TEST_DATA = json.load(f)


async def create_database_engine():
    """Create and return a database engine."""
    # Create the engine
    engine = create_async_engine(settings.database_url)
    
    # Create an async session
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Return both for later use
    return engine, async_session


async def create_test_user(session, stripe_customer_id):
    """Create a test user with the given Stripe customer ID."""
    print("\n=== Creating Test User ===")
    
    # Check if user with this email already exists
    result = await session.execute(
        select(User).where(User.email == "test_stripe@example.com")
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        print(f"User already exists: {existing_user.username} (ID: {existing_user.id})")
        
        # Update Stripe customer ID if it's not set
        if not existing_user.stripe_customer_id:
            existing_user.stripe_customer_id = stripe_customer_id
            await session.commit()
            print(f"Updated Stripe customer ID: {stripe_customer_id}")
            
        return existing_user
    
    # Create new user
    hashed_password = get_password_hash("testpassword")
    
    new_user = User(
        username="test_stripe_user",
        email="test_stripe@example.com",
        hashed_password=hashed_password,
        is_verified=True,
        stripe_customer_id=stripe_customer_id
    )
    
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    
    print(f"Created new user: {new_user.username} (ID: {new_user.id})")
    print(f"Stripe customer ID: {new_user.stripe_customer_id}")
    
    # Create initial credit record for user
    await session.execute(
        insert(UserCredit).values(
            user_id=new_user.id,
            balance=Decimal('0.00')
        )
    )
    await session.commit()
    
    print(f"Created initial credit record with 0 balance")
    
    return new_user


async def create_test_plans(session):
    """Create test plans that match our Stripe prices."""
    print("\n=== Creating Test Plans ===")
    
    created_plans = []
    
    # Process one-time plans
    one_time_prices = [p for p in STRIPE_TEST_DATA["prices"] if p["type"] == "one_time"]
    for price in one_time_prices:
        # Get or create plan
        result = await session.execute(
            select(Plan).where(Plan.stripe_price_id == price["id"])
        )
        existing_plan = result.scalar_one_or_none()
        
        if existing_plan:
            print(f"One-time plan already exists: {existing_plan.name} (ID: {existing_plan.id})")
            created_plans.append(existing_plan)
            continue
            
        # Determine tier based on credit amount
        tier = PlanTier.TIER_100
        if price["credits"] >= 1000:
            tier = PlanTier.TIER_1000
        elif price["credits"] >= 500:
            tier = PlanTier.TIER_500
        elif price["credits"] >= 300:
            tier = PlanTier.TIER_300
        elif price["credits"] >= 200:
            tier = PlanTier.TIER_200
        
        # Create new plan
        new_plan = Plan(
            name=f"{price['credits']} Credits Package",
            tier=tier,
            credit_amount=Decimal(price["credits"]),
            price=Decimal(price["amount"]) / 100,  # Convert cents to dollars
            is_active=True,
            description=f"One-time purchase of {price['credits']} credits",
            stripe_price_id=price["id"],
            stripe_product_id=price["product_id"]
        )
        
        session.add(new_plan)
        await session.commit()
        await session.refresh(new_plan)
        
        print(f"Created one-time plan: {new_plan.name} (ID: {new_plan.id})")
        print(f"  Credits: {new_plan.credit_amount}, Price: ${new_plan.price}")
        print(f"  Stripe Price ID: {new_plan.stripe_price_id}")
        
        created_plans.append(new_plan)
    
    # Process subscription plans
    subscription_prices = [p for p in STRIPE_TEST_DATA["prices"] if p["type"] == "subscription"]
    for price in subscription_prices:
        # Get or create plan
        result = await session.execute(
            select(Plan).where(Plan.stripe_price_id == price["id"])
        )
        existing_plan = result.scalar_one_or_none()
        
        if existing_plan:
            print(f"Subscription plan already exists: {existing_plan.name} (ID: {existing_plan.id})")
            created_plans.append(existing_plan)
            continue
            
        # Determine tier based on credit amount
        tier = PlanTier.TIER_100
        if price["credits"] >= 1000:
            tier = PlanTier.TIER_1000
        elif price["credits"] >= 500:
            tier = PlanTier.TIER_500
        elif price["credits"] >= 300:
            tier = PlanTier.TIER_300
        elif price["credits"] >= 200:
            tier = PlanTier.TIER_200
        
        # Create new plan
        new_plan = Plan(
            name=f"{price['credits']} Credits Monthly",
            tier=tier,
            credit_amount=Decimal(price["credits"]),
            price=Decimal(price["amount"]) / 100,  # Convert cents to dollars
            is_active=True,
            description=f"Monthly subscription with {price['credits']} credits",
            stripe_price_id=price["id"],
            stripe_product_id=price["product_id"]
        )
        
        session.add(new_plan)
        await session.commit()
        await session.refresh(new_plan)
        
        print(f"Created subscription plan: {new_plan.name} (ID: {new_plan.id})")
        print(f"  Credits: {new_plan.credit_amount}, Price: ${new_plan.price}")
        print(f"  Stripe Price ID: {new_plan.stripe_price_id}")
        
        created_plans.append(new_plan)
    
    return created_plans


async def main():
    """Main function to prepare the test environment."""
    print("=== Preparing Test Environment for Stripe Integration ===")
    
    # Create database engine and session
    engine, async_session = await create_database_engine()
    
    # Use the session to create test data
    async with async_session() as session:
        # Create test user with Stripe customer ID
        user = await create_test_user(session, STRIPE_TEST_DATA["customer_id"])
        
        # Create test plans matching Stripe prices
        plans = await create_test_plans(session)
    
    # Clean up
    await engine.dispose()
    
    # Print summary
    print("\n=== Test Environment Preparation Complete ===")
    print(f"- Test user created: ID={user.id}, Email={user.email}")
    print(f"- Plans created: {len(plans)}")
    print("\nYou can now run test scripts to verify the Stripe integration.")


if __name__ == "__main__":
    asyncio.run(main())