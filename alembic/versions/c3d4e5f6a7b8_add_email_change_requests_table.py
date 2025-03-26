"""Add email change requests table

Revision ID: c3d4e5f6a7b8
Revises: b3935b697a72
Create Date: 2025-03-24 17:57:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b3935b697a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create email_change_requests table
    op.create_table(
        'email_change_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('current_email', sa.String(length=100), nullable=False),
        sa.Column('new_email', sa.String(length=100), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, 
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column('completed', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    
    # Create index on user_id for faster lookups
    op.create_index(op.f('ix_email_change_requests_id'), 'email_change_requests', ['id'], unique=False)
    op.create_index(op.f('ix_email_change_requests_user_id'), 'email_change_requests', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop the email_change_requests table
    op.drop_index(op.f('ix_email_change_requests_user_id'), table_name='email_change_requests')
    op.drop_index(op.f('ix_email_change_requests_id'), table_name='email_change_requests')
    op.drop_table('email_change_requests')