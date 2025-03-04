"""Add Google OAuth fields

Revision ID: add_google_oauth_fields
Revises: 4c723b89c716
Create Date: 2025-03-04 20:43:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3935b697a72'  # Changed to a proper UUID format
down_revision: Union[str, None] = '4c723b89c716'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make hashed_password nullable for OAuth-only users
    op.alter_column('users', 'hashed_password',
               existing_type=sa.VARCHAR(length=255),
               nullable=True)
    
    # Add google_id column (String, nullable, unique)
    op.add_column('users', sa.Column('google_id', sa.String(length=255), nullable=True, unique=True))
    
    # Add auth_type column (String(20), default="password", nullable=False)
    op.add_column('users', sa.Column('auth_type', sa.String(length=20), nullable=False, server_default="password"))
    
    # Create a unique index on google_id
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)


def downgrade() -> None:
    # Drop the index
    op.drop_index(op.f('ix_users_google_id'), table_name='users')
    
    # Drop the columns
    op.drop_column('users', 'auth_type')
    op.drop_column('users', 'google_id')
    
    # Make hashed_password non-nullable again
    op.alter_column('users', 'hashed_password',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)