"""add_stripe_price_id_to_subscriptions

Revision ID: 953b24ea4f22
Revises: a573df5bf723
Create Date: 2025-05-08 16:56:04.387391

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '953b24ea4f22'
down_revision: Union[str, None] = 'a573df5bf723'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('stripe_price_id', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'stripe_price_id')
