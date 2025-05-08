"""add_testing_fields_to_plans

Revision ID: 910d6692dbb9
Revises: 8b094d1bb681
Create Date: 2025-05-08 17:08:23.370629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '910d6692dbb9'
down_revision: Union[str, None] = '8b094d1bb681'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plans', sa.Column('is_trial_eligible', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('plans', sa.Column('is_public', sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column('plans', sa.Column('price_cents', sa.Integer(), nullable=True))
    op.add_column('plans', sa.Column('credits_awarded', sa.Integer(), nullable=True))
    op.add_column('plans', sa.Column('trial_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('plans', 'trial_days')
    op.drop_column('plans', 'credits_awarded')
    op.drop_column('plans', 'price_cents')
    op.drop_column('plans', 'is_public')
    op.drop_column('plans', 'is_trial_eligible')
