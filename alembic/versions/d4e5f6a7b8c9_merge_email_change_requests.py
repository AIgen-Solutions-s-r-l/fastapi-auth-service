"""merge email change requests

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8, d8f45e2a1b3c
Create Date: 2025-03-24 18:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Multiple heads being merged
down_revision = ('c3d4e5f6a7b8', 'd8f45e2a1b3c')


def upgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass


def downgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass