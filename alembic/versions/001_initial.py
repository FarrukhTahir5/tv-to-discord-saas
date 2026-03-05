"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users table ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        # Webhook
        sa.Column("webhook_token", sa.String(), unique=True, nullable=False),
        sa.Column("webhook_token_created_at", sa.DateTime(), server_default=sa.func.now()),
        # Discord
        sa.Column("discord_webhook_url", sa.String(), nullable=True),
        # Alert defaults
        sa.Column("default_exchange", sa.String(), server_default="NASDAQ"),
        sa.Column("default_symbol", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), server_default="UTC"),
        # Usage limits
        sa.Column("daily_limit", sa.Integer(), server_default="10"),
        sa.Column("alerts_used_today", sa.Integer(), server_default="0"),
        sa.Column("alerts_reset_at", sa.Date(), nullable=True),
        # Billing
        sa.Column("plan", sa.String(), server_default="free"),
        sa.Column("ls_customer_id", sa.String(), nullable=True),
        sa.Column("ls_subscription_id", sa.String(), nullable=True),
        sa.Column("subscription_status", sa.String(), server_default="inactive"),
        # Meta
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_webhook_token", "users", ["webhook_token"])

    # --- Alerts log table ---
    op.create_table(
        "alerts_log",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(), unique=True, nullable=False),
        # Raw + parsed
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("parsed_symbol", sa.String(), nullable=True),
        sa.Column("parsed_message", sa.String(), nullable=True),
        # Status tracking
        sa.Column("status", sa.String(), server_default="queued"),
        sa.Column("error_stage", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        # Metrics
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("discord_status_code", sa.Integer(), nullable=True),
        sa.Column("request_ip", sa.String(), nullable=True),
        # Meta
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_log_user_id", "alerts_log", ["user_id"])
    op.create_index("ix_alerts_log_idempotency_key", "alerts_log", ["idempotency_key"])
    op.create_index("ix_alerts_log_status", "alerts_log", ["status"])


def downgrade() -> None:
    op.drop_table("alerts_log")
    op.drop_table("users")
