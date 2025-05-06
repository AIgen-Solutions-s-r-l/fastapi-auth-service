"""create_processed_stripe_events_table

Revision ID: c317a4c7fcf9
Revises: 0f1a7f1ea92f
Create Date: 2025-05-06 17:34:53.660582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c317a4c7fcf9'
down_revision: Union[str, None] = '0f1a7f1ea92f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
