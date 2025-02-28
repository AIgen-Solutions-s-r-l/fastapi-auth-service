"""
Script to update subscription tiers according to the new 5-tier system.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text
from app.core.database import engine
from app.log.logging import logger


async def update_subscription_tiers():
    """Update subscription tiers to the new 5-tier system."""
    try:
        logger.info("Starting subscription tier update", extra={
            "event_type": "subscription_tier_update_start"
        })

        async with engine.begin() as conn:
            # Update existing plans - execute each statement separately
            # Update basic tier
            await conn.execute(text("""
            UPDATE plans SET
                name = '100 Applications Package',
                tier = 'tier_100',
                credit_amount = 100.00,
                price = 35.00,
                description = 'Entry-level plan with 100 application credits'
            WHERE tier = 'basic';
            """))
            logger.info("Updated basic tier to 100 Applications Package", extra={
                "event_type": "subscription_tier_update_basic"
            })

            # Update standard tier
            await conn.execute(text("""
            UPDATE plans SET
                name = '500 Applications Package',
                tier = 'tier_500',
                credit_amount = 500.00,
                price = 115.00,
                description = 'Medium plan with 500 application credits'
            WHERE tier = 'standard';
            """))
            logger.info("Updated standard tier to 500 Applications Package", extra={
                "event_type": "subscription_tier_update_standard"
            })

            # Update premium tier
            await conn.execute(text("""
            UPDATE plans SET
                name = '1000 Applications Package',
                tier = 'tier_1000',
                credit_amount = 1000.00,
                price = 175.00,
                description = 'Premium plan with 1000 application credits'
            WHERE tier = 'premium';
            """))
            logger.info("Updated premium tier to 1000 Applications Package", extra={
                "event_type": "subscription_tier_update_premium"
            })

            # Check if new plans already exist
            result = await conn.execute(text("""
            SELECT COUNT(*) FROM plans WHERE tier IN ('tier_200', 'tier_300');
            """))
            count = result.scalar()

            if count == 0:
                # Add new plans - execute each insert separately
                await conn.execute(text("""
                INSERT INTO plans (name, tier, credit_amount, price, is_active, description, created_at, updated_at)
                VALUES ('200 Applications Package', 'tier_200', 200.00, 59.00, true, 'Basic plan with 200 application credits', now(), now());
                """))
                
                await conn.execute(text("""
                INSERT INTO plans (name, tier, credit_amount, price, is_active, description, created_at, updated_at)
                VALUES ('300 Applications Package', 'tier_300', 300.00, 79.00, true, 'Standard plan with 300 application credits', now(), now());
                """))
                
                logger.info("Added new tier plans: 200 and 300 Applications Packages", extra={
                    "event_type": "subscription_tier_new_plans_added"
                })
            else:
                logger.info("New tier plans already exist, skipping insertion", extra={
                    "event_type": "subscription_tier_new_plans_skipped"
                })

            # Verify the update
            result = await conn.execute(text("""
            SELECT id, name, tier, credit_amount, price FROM plans ORDER BY credit_amount;
            """))
            plans = result.fetchall()
            
            logger.info(f"Updated subscription tiers: {len(plans)} plans in the database", extra={
                "event_type": "subscription_tier_update_complete",
                "plan_count": len(plans)
            })
            
            for plan in plans:
                logger.info(f"Plan: {plan.name}, Tier: {plan.tier}, Credits: {plan.credit_amount}, Price: {plan.price}", extra={
                    "event_type": "subscription_tier_plan_details",
                    "plan_id": plan.id,
                    "plan_name": plan.name,
                    "plan_tier": plan.tier,
                    "plan_credits": float(plan.credit_amount),
                    "plan_price": float(plan.price)
                })

        logger.info("Subscription tier update completed successfully", extra={
            "event_type": "subscription_tier_update_success"
        })
        
    except Exception as e:
        logger.exception(f"Error updating subscription tiers: {str(e)}", extra={
            "event_type": "subscription_tier_update_error",
            "error": str(e)
        })
        raise


def main():
    """Main function to run the subscription tier update."""
    try:
        asyncio.run(update_subscription_tiers())
    except KeyboardInterrupt:
        logger.info("Subscription tier update interrupted", extra={
            "event_type": "subscription_tier_update_interrupted"
        })
    except Exception as e:
        logger.exception(f"Subscription tier update error: {str(e)}", extra={
            "event_type": "subscription_tier_update_error",
            "error": str(e)
        })
        sys.exit(1)


if __name__ == "__main__":
    main()