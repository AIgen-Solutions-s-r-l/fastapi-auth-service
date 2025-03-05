"""remove username field

Revision ID: e66712ccad45
Revises: c97acf42b2f8
Create Date: 2025-03-05 13:19:12.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e66712ccad45'
down_revision: Union[str, None] = 'c97acf42b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop username column from users table
    op.drop_column('users', 'username')


def downgrade() -> None:
    # Add username column back to users table
    op.add_column('users', sa.Column('username', sa.String(100), nullable=True))
