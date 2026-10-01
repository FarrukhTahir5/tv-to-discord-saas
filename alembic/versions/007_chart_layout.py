"""Add chart layout and default interval to users

Revision ID: 007_chart_layout
Revises: 006_lemonsqueezy
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_chart_layout'
down_revision: Union[str, None] = '006_lemonsqueezy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('chart_layout_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('default_interval', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'default_interval')
    op.drop_column('users', 'chart_layout_id')
