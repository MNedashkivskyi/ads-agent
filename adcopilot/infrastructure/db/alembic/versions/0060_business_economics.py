"""Add business_economics table (Phase 5).

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_economics",
        sa.Column("account_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("avg_order_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("profit_margin_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("customer_ltv", sa.Numeric(14, 2), nullable=True),
        sa.Column("target_roas", sa.Numeric(8, 2), nullable=True),
        sa.Column("default_lead_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("business_economics")
