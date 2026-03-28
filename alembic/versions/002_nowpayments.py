"""migrate to nowpayments

Revision ID: 002_nowpayments
Revises: 001_initial
Create Date: 2025-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_nowpayments'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nowpayments column
    op.add_column('users', sa.Column('np_subscriber_id', sa.String(), nullable=True))
    
    # Drop lemonsqueezy columns
    op.drop_column('users', 'ls_customer_id')
    op.drop_column('users', 'ls_subscription_id')


def downgrade() -> None:
    # Re-add lemonsqueezy columns
    op.add_column('users', sa.Column('ls_customer_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('ls_subscription_id', sa.String(), nullable=True))
    
    # Drop nowpayments column
    op.drop_column('users', 'np_subscriber_id')
