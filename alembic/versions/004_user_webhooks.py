"""User webhooks

Revision ID: 004_user_webhooks
Revises: 003_gumroad
Create Date: 2026-04-03 23:16:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004_user_webhooks'
down_revision: Union[str, None] = '003_gumroad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Create user_webhooks table
    op.create_table(
        'user_webhooks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), server_default='Primary Channel', nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )
    op.create_index(op.f('ix_user_webhooks_user_id'), 'user_webhooks', ['user_id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_user_webhooks_user_id'), table_name='user_webhooks')
    op.drop_table('user_webhooks')
