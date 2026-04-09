"""Replace nowpayments/gumroad fields with lemonsqueezy fields

Revision ID: 006_lemonsqueezy
Revises: 005_add_trial_system
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_lemonsqueezy'
down_revision: Union[str, None] = '005_add_trial_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add LemonSqueezy columns
    op.add_column('users', sa.Column('ls_customer_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('ls_subscription_id', sa.String(), nullable=True))

    # Remove old payment columns
    op.drop_column('users', 'np_subscriber_id')
    op.drop_column('users', 'gumroad_id')


def downgrade() -> None:
    # Restore old payment columns
    op.add_column('users', sa.Column('np_subscriber_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('gumroad_id', sa.String(), nullable=True))

    # Remove LemonSqueezy columns
    op.drop_column('users', 'ls_subscription_id')
    op.drop_column('users', 'ls_customer_id')
