"""add stripe integration

Revision ID: 93a5cbf21d89
Revises: c97acf42b2f8
Create Date: 2025-02-28 21:58:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '93a5cbf21d89'
down_revision: Union[str, None] = 'c97acf42b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Stripe-related columns to User model
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(100), nullable=True))
    
    # Add Stripe-related columns to Plan model
    op.add_column('plans', sa.Column('stripe_price_id', sa.String(100), nullable=True))
    op.add_column('plans', sa.Column('stripe_product_id', sa.String(100), nullable=True))
    
    # Add Stripe-related columns to Subscription model
    op.add_column('subscriptions', sa.Column('stripe_subscription_id', sa.String(100), nullable=True))
    op.add_column('subscriptions', sa.Column('stripe_customer_id', sa.String(100), nullable=True))
    op.add_column('subscriptions', sa.Column('status', sa.String(50), server_default='active', nullable=False))


def downgrade() -> None:
    # Remove Stripe-related columns from Subscription model
    op.drop_column('subscriptions', 'status')
    op.drop_column('subscriptions', 'stripe_customer_id')
    op.drop_column('subscriptions', 'stripe_subscription_id')
    
    # Remove Stripe-related columns from Plan model
    op.drop_column('plans', 'stripe_product_id')
    op.drop_column('plans', 'stripe_price_id')
    
    # Remove Stripe-related columns from User model
    op.drop_column('users', 'stripe_customer_id')