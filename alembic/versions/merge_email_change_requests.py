"""merge email change requests

Revision ID: merge_email_change_requests
Revises: add_email_change_requests, d8f45e2a1b3c
Create Date: 2025-03-24 18:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_email_change_requests'
down_revision = None
branch_labels = None
depends_on = None

# Multiple heads being merged
depends_on = ('add_email_change_requests', 'd8f45e2a1b3c')


def upgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass


def downgrade() -> None:
    # This is a merge migration, no schema changes needed
    pass