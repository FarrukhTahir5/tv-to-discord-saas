"""Add trial system

Revision ID: 005_add_trial_system
Revises: 004_user_webhooks
Create Date: 2026-04-07 19:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005_add_trial_system'
down_revision: Union[str, None] = '004_user_webhooks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('users', sa.Column('trial_expires_at', sa.DateTime(), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'trial_expires_at')
