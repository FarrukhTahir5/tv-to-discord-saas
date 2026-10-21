"""Add outreach leads and app settings

Revision ID: 010_outreach
Revises: 009_subscription_renews_at
Create Date: 2026-10-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010_outreach'
down_revision: Union[str, None] = '009_subscription_renews_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outreach_leads',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('community', sa.String(), nullable=False),
        sa.Column('niche', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('hook', sa.Text(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='new'),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('followed_up_at', sa.DateTime(), nullable=True),
        sa.Column('replied_at', sa.DateTime(), nullable=True),
        sa.Column('message_id', sa.String(), nullable=True),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('unsubscribe_token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_outreach_leads_email', 'outreach_leads', ['email'], unique=True)
    op.create_index('ix_outreach_leads_status', 'outreach_leads', ['status'])
    op.create_unique_constraint('uq_outreach_unsubscribe_token', 'outreach_leads', ['unsubscribe_token'])

    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
    op.drop_index('ix_outreach_leads_status', 'outreach_leads')
    op.drop_index('ix_outreach_leads_email', 'outreach_leads')
    op.drop_table('outreach_leads')
