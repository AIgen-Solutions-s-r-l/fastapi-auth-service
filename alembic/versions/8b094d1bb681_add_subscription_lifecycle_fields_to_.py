"""add_subscription_lifecycle_fields_to_subscriptions

Revision ID: 8b094d1bb681
Revises: ee5cc43c0724
Create Date: 2025-05-08 17:03:16.150489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8b094d1bb681'
down_revision: Union[str, None] = 'ee5cc43c0724'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('subscriptions', sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('subscriptions', sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'canceled_at')
    op.drop_column('subscriptions', 'cancel_at_period_end')
    op.drop_column('subscriptions', 'current_period_end')
    op.drop_column('subscriptions', 'current_period_start')
