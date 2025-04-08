"""remove_tier_column_from_plans

Revision ID: f5c4f35a6afe
Revises: 8f156762c22b
Create Date: 2025-04-08 23:48:03.130303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5c4f35a6afe'
down_revision: Union[str, None] = '8f156762c22b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop tier column from plans table
    op.drop_column('plans', 'tier')


def downgrade() -> None:
    # Add tier column back to plans table
    op.add_column('plans', sa.Column('tier', sa.String(20), nullable=False, server_default='custom'))
    
    # Remove the server_default after the column is added
    op.alter_column('plans', 'tier', server_default=None)
