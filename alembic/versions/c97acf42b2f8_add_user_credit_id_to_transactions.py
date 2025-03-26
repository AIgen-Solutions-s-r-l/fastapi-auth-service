"""add_user_credit_id_to_transactions

Revision ID: c97acf42b2f8
Revises: a1b2c3d4e5f6
Create Date: 2025-02-06 20:07:31.953325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c97acf42b2f8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add user_credit_id column
    op.add_column('credit_transactions',
        sa.Column('user_credit_id', sa.Integer(), nullable=False)
    )
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_credit_transactions_user_credit',
        'credit_transactions', 'user_credits',
        ['user_credit_id'], ['id']
    )


def downgrade() -> None:
    # Drop foreign key constraint
    op.drop_constraint(
        'fk_credit_transactions_user_credit',
        'credit_transactions',
        type_='foreignkey'
    )
    
    # Drop column
    op.drop_column('credit_transactions', 'user_credit_id')
