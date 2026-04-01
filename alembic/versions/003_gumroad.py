"""add gumroad column

Revision ID: 003_gumroad
Revises: 002_nowpayments
Create Date: 2026-04-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_gumroad'
down_revision: Union[str, None] = '002_nowpayments'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add gumroad column
    op.add_column('users', sa.Column('gumroad_id', sa.String(), nullable=True))


def downgrade() -> None:
    # Drop gumroad column
    op.drop_column('users', 'gumroad_id')
