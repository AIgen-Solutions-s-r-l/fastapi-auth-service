"""merge stripe integration

Revision ID: 8a5bc96f2d47
Revises: 98f2bfc6cbd1, 93a5cbf21d89
Create Date: 2025-02-28 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '8a5bc96f2d47'
down_revision: Union[str, None] = ('98f2bfc6cbd1', '93a5cbf21d89')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass