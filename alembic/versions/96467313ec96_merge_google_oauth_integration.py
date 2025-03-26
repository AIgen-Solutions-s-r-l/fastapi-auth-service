"""merge_google_oauth_integration

Revision ID: 96467313ec96
Revises: b3935b697a72, 8a5bc96f2d47
Create Date: 2025-03-04 20:47:08.667998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96467313ec96'
down_revision: Union[str, None] = ('b3935b697a72', '8a5bc96f2d47')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
