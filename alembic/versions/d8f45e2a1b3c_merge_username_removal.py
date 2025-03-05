"""merge username removal

Revision ID: d8f45e2a1b3c
Revises: 96467313ec96, e66712ccad45
Create Date: 2025-03-05 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f45e2a1b3c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Include both parent revisions
depends_on = ['96467313ec96', 'e66712ccad45']


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass