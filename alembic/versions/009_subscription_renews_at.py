"""Add subscription_renews_at for showing the next renewal date

Revision ID: 009_subscription_renews_at
Revises: 008_subscription_ends_at
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009_subscription_renews_at'
down_revision: Union[str, None] = '008_subscription_ends_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('subscription_renews_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'subscription_renews_at')
