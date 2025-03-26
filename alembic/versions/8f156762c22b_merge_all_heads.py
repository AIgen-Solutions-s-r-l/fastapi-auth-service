"""merge_all_heads

Revision ID: 8f156762c22b
Revises: d4e5f6a7b8c9, 96467313ec96, e66712ccad45
Create Date: 2025-03-26 20:46:18.259576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f156762c22b'
down_revision: Union[str, None] = ('d4e5f6a7b8c9', '96467313ec96', 'e66712ccad45')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
