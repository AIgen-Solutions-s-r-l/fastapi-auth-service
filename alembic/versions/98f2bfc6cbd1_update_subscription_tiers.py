"""update_subscription_tiers

Revision ID: 98f2bfc6cbd1
Revises: 68d538faebe3
Create Date: 2025-02-26 15:34:58.627939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98f2bfc6cbd1'
down_revision: Union[str, None] = '68d538faebe3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing plans
    op.execute("""
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
    """)
    
    # Add new plans
    op.execute("""
    INSERT INTO plans (name, tier, credit_amount, price, is_active, description, created_at, updated_at)
    VALUES
        ('200 Applications Package', 'tier_200', 200.00, 59.00, true, 'Basic plan with 200 application credits', now(), now()),
        ('300 Applications Package', 'tier_300', 300.00, 79.00, true, 'Standard plan with 300 application credits', now(), now());
    """)


def downgrade() -> None:
    # Revert new plans
    op.execute("""
    DELETE FROM plans WHERE tier IN ('tier_200', 'tier_300');
    """)
    
    # Revert existing plans
    op.execute("""
    UPDATE plans SET
        name = 'Basic Plan',
        tier = 'basic',
        credit_amount = 100.00,
        price = 9.99,
        description = 'Entry-level plan with 100 credits per month'
    WHERE tier = 'tier_100';

    UPDATE plans SET
        name = 'Standard Plan',
        tier = 'standard',
        credit_amount = 500.00,
        price = 29.99,
        description = 'Standard plan with 500 credits per month'
    WHERE tier = 'tier_500';

    UPDATE plans SET
        name = 'Premium Plan',
        tier = 'premium',
        credit_amount = 1500.00,
        price = 79.99,
        description = 'Premium plan with 1500 credits per month'
    WHERE tier = 'tier_1000';
    """)
