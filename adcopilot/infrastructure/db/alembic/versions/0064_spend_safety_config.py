"""Add spend_safety_config table (spend-safety system).

Revision ID: 0064
Revises: 0063
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spend_safety_config",
        sa.Column("account_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("monthly_spend_cap_micros", sa.BigInteger, nullable=True),
        sa.Column("daily_spend_cap_micros", sa.BigInteger, nullable=True),
        sa.Column("per_campaign_daily_cap_micros", sa.BigInteger, nullable=True),
        sa.Column(
            "max_budget_increase_pct", sa.Numeric(6, 2), nullable=False, server_default="50.0"
        ),
        sa.Column(
            "warning_threshold_pct", sa.Numeric(5, 2), nullable=False, server_default="80.0"
        ),
        sa.Column(
            "auto_pause_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("spend_safety_config")
