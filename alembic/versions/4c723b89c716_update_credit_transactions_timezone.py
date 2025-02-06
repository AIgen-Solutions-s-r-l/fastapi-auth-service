"""update_credit_transactions_timezone

Revision ID: 4c723b89c716
Revises: c97acf42b2f8
Create Date: 2025-02-06 20:10:18.462591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4c723b89c716'
down_revision: Union[str, None] = 'c97acf42b2f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter created_at column to use timezone
    op.alter_column('credit_transactions', 'created_at',
                   type_=sa.DateTime(timezone=True),
                   existing_type=sa.DateTime(),
                   existing_nullable=False)


def downgrade() -> None:
    # Revert created_at column to not use timezone
    op.alter_column('credit_transactions', 'created_at',
                   type_=sa.DateTime(),
                   existing_type=sa.DateTime(timezone=True),
                   existing_nullable=False)
