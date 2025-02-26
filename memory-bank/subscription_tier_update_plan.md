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

### 1. Update the PlanTier Enum in `app/models/plan.py`
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

### 2. Create a Database Migration
Create a new Alembic migration to:
- Update the existing plans with new names, credit amounts, and prices
- Add the new plans that don't exist yet

Migration SQL:
```sql
-- Update existing plans
UPDATE plans SET 
    name = '100 Applications Package', 
    tier = 'tier_100',
    credit_amount = 100.00,
    price = 35.00,
    description = 'Entry-level plan with 100 application credits'
WHERE tier = 'basic';

UPDATE plans SET 
    name = '500 Applications Package', 
    tier = 'tier_500',
    credit_amount = 500.00,
    price = 115.00,
    description = 'Medium plan with 500 application credits'
WHERE tier = 'standard';

UPDATE plans SET 
    name = '1000 Applications Package', 
    tier = 'tier_1000',
    credit_amount = 1000.00,
    price = 175.00,
    description = 'Premium plan with 1000 application credits'
WHERE tier = 'premium';

-- Add new plans
INSERT INTO plans (name, tier, credit_amount, price, is_active, description)
VALUES 
    ('200 Applications Package', 'tier_200', 200.00, 59.00, true, 'Basic plan with 200 application credits'),
    ('300 Applications Package', 'tier_300', 300.00, 79.00, true, 'Standard plan with 300 application credits');
```

### 3. Update Any References to Plan Tiers
- Search for any code that references the old tier names (BASIC, STANDARD, PREMIUM)
- Update any business logic that might depend on specific tier names
- Ensure the credit service and other components work with the new tier structure

### 4. Testing
- Test plan creation
- Test plan upgrades between the new tiers
- Test subscription renewals
- Verify credit amounts are correct for each tier

### 5. Documentation Updates
- Update any documentation that references the old tier structure
- Update API documentation if necessary