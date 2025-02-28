# Subscription Tier Update Plan

## Current System
The current system has 4 plan tiers defined in `app/models/plan.py`:
- BASIC
- STANDARD
- PREMIUM
- CUSTOM

The database initialization in `alembic/versions/add_email_and_plan_tables.py` creates 3 plans:
- Basic Plan (100 credits, $9.99)
- Standard Plan (500 credits, $29.99)
- Premium Plan (1500 credits, $79.99)

## New System Requirements
Based on the provided image, the new system should have 5 tiers:
- 100 Applications Package ($35)
- 200 Applications Package ($59)
- 300 Applications Package ($79)
- 500 Applications Package ($115)
- 1000 Applications Package ($175)

## Implementation Steps

### 1. ✅ Update the PlanTier Enum in `app/models/plan.py`
```python
class PlanTier(str, Enum):
    """Plan tier levels based on application count."""
    TIER_100 = "tier_100"
    TIER_200 = "tier_200"
    TIER_300 = "tier_300"
    TIER_500 = "tier_500"
    TIER_1000 = "tier_1000"
    CUSTOM = "custom"  # Keep custom tier for special cases
```

### 2. ✅ Create a Database Update Script
Due to issues with Alembic migrations (multiple heads), we created a direct database update script:

```python
# update_subscription_tiers.py
async def update_subscription_tiers():
    """Update subscription tiers to the new 5-tier system."""
    try:
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
            
            # Add new plans
            await conn.execute(text("""
            INSERT INTO plans (name, tier, credit_amount, price, is_active, description, created_at, updated_at)
            VALUES ('200 Applications Package', 'tier_200', 200.00, 59.00, true, 'Basic plan with 200 application credits', now(), now());
            """))
            
            await conn.execute(text("""
            INSERT INTO plans (name, tier, credit_amount, price, is_active, description, created_at, updated_at)
            VALUES ('300 Applications Package', 'tier_300', 300.00, 79.00, true, 'Standard plan with 300 application credits', now(), now());
            """))
```

### 3. ✅ Update Any References to Plan Tiers
We searched for any code that references the old tier names (BASIC, STANDARD, PREMIUM) and found no direct references in the codebase. The tier names are stored in the database and accessed through the PlanTier enum.

### 4. ✅ Testing
We ran the update script and verified that all 5 tiers are now in the database with the correct credit amounts and prices:
- 100 Applications Package: 100 credits, $35
- 200 Applications Package: 200 credits, $59
- 300 Applications Package: 300 credits, $79
- 500 Applications Package: 500 credits, $115
- 1000 Applications Package: 1000 credits, $175

### 5. ✅ Documentation Updates
- Updated Memory Bank files to reflect the completion of this task
- Updated the PlanTier enum documentation to reflect the new tier structure