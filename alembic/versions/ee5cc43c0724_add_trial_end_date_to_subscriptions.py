"""add_trial_end_date_to_subscriptions

Revision ID: ee5cc43c0724
Revises: 953b24ea4f22
Create Date: 2025-05-08 17:01:23.595054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee5cc43c0724'
down_revision: Union[str, None] = '953b24ea4f22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('trial_end_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'trial_end_date')
