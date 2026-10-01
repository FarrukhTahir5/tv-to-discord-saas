"""Add subscription_ends_at so cancelled subscriptions keep Pro until period end

Revision ID: 008_subscription_ends_at
Revises: 007_chart_layout
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008_subscription_ends_at'
down_revision: Union[str, None] = '007_chart_layout'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('subscription_ends_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'subscription_ends_at')
