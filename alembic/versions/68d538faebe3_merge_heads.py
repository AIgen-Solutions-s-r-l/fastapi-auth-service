"""merge_heads

Revision ID: 68d538faebe3
Revises: 4c723b89c716, b2c3d4e5f6a7
Create Date: 2025-02-26 15:34:48.977332

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68d538faebe3'
down_revision: Union[str, None] = ('4c723b89c716', 'b2c3d4e5f6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
