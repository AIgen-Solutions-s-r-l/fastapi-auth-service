"""
Script to update the database schema for Stripe integration.
This script directly alters the tables without using Alembic migrations.
"""

import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.log.logging import logger


async def update_schema():
    """Update the database schema for Stripe integration."""
    # Create engine
    engine = create_async_engine(settings.database_url)
    
    # Start a transaction
    async with engine.begin() as conn:
        logger.info("Starting direct schema update for Stripe integration", event_type="schema_update_start")
        
        try:
            # 1. Add Stripe-related columns to User model
            logger.info("Adding stripe_customer_id column to users table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100)")
            )
            
            # 2. Add Stripe-related columns to Plan model
            logger.info("Adding stripe_price_id column to plans table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS stripe_price_id VARCHAR(100)")
            )
            
            logger.info("Adding stripe_product_id column to plans table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE plans ADD COLUMN IF NOT EXISTS stripe_product_id VARCHAR(100)")
            )
            
            # 3. Add Stripe-related columns to Subscription model
            logger.info("Adding stripe_subscription_id column to subscriptions table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(100)")
            )
            
            logger.info("Adding stripe_customer_id column to subscriptions table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100)")
            )
            
            logger.info("Adding status column to subscriptions table", event_type="schema_update_progress")
            await conn.execute(
                sa.text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active' NOT NULL")
            )
            
            logger.info("Schema update for Stripe integration completed successfully", event_type="schema_update_complete")
        
        except Exception as e:
            logger.error(f"Error updating schema: {str(e)}", event_type="schema_update_error", error=str(e))
            raise
        
    # Close connection
    await engine.dispose()


if __name__ == "__main__":
    logger.info("Running direct database schema update for Stripe integration")
    asyncio.run(update_schema())
    logger.info("Script completed")