"""Add email verification and plan/subscription tables

Revision ID: b2c3d4e5f6a7
Revises: c97acf42b2f8
Create Date: 2025-02-25 22:47:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'c97acf42b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to users table
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('verification_token', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('verification_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create email_verification_tokens table
    op.create_table('email_verification_tokens',
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('token')
    )
    
    # Create plans table
    op.create_table('plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('tier', sa.String(length=20), nullable=False),
        sa.Column('credit_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plans_id'), 'plans', ['id'], unique=False)
    
    # Create subscriptions table
    op.create_table('subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('renewal_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_renewal_date', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_subscriptions_id'), 'subscriptions', ['id'], unique=False)
    
    # Add fields to credit_transactions for plan relationship
    op.add_column('credit_transactions', sa.Column('plan_id', sa.Integer(), nullable=True))
    op.add_column('credit_transactions', sa.Column('subscription_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_credit_transactions_plan_id', 'credit_transactions', 'plans', ['plan_id'], ['id'])
    op.create_foreign_key('fk_credit_transactions_subscription_id', 'credit_transactions', 'subscriptions', ['subscription_id'], ['id'])
    
    # Add basic plans
    op.execute("""
    INSERT INTO plans (name, tier, credit_amount, price, is_active, description)
    VALUES 
        ('Basic Plan', 'basic', 100.00, 9.99, true, 'Entry-level plan with 100 credits per month'),
        ('Standard Plan', 'standard', 500.00, 29.99, true, 'Standard plan with 500 credits per month'),
        ('Premium Plan', 'premium', 1500.00, 79.99, true, 'Premium plan with 1500 credits per month')
    """)


def downgrade() -> None:
    # Remove foreign keys from credit_transactions
    op.drop_constraint('fk_credit_transactions_subscription_id', 'credit_transactions', type_='foreignkey')
    op.drop_constraint('fk_credit_transactions_plan_id', 'credit_transactions', type_='foreignkey')
    
    # Remove columns from credit_transactions
    op.drop_column('credit_transactions', 'subscription_id')
    op.drop_column('credit_transactions', 'plan_id')
    
    # Drop subscriptions table
    op.drop_index(op.f('ix_subscriptions_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    
    # Drop plans table
    op.drop_index(op.f('ix_plans_id'), table_name='plans')
    op.drop_table('plans')
    
    # Drop email_verification_tokens table
    op.drop_table('email_verification_tokens')
    
    # Remove columns from users table
    op.drop_column('users', 'verification_token_expires_at')
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'is_verified')