"""Create ad_experiments table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ad_experiments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("campaign_resource_name", sa.Text(), nullable=False),
        sa.Column("ad_group_resource_name", sa.Text(), nullable=False),
        sa.Column("control_ad_resource_name", sa.Text(), nullable=False),
        sa.Column("variant_ad_resource_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("min_impressions", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("confidence_threshold", sa.Float(), nullable=False, server_default="0.95"),
        sa.Column("winner", sa.String(32), nullable=True),
        sa.Column("control_metrics", sa.JSON(), nullable=True),
        sa.Column("variant_metrics", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["account_id"], ["google_ads_accounts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ad_experiments_account_id", "ad_experiments", ["account_id"])
    op.create_index("ix_ad_experiments_status", "ad_experiments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ad_experiments_status", "ad_experiments")
    op.drop_index("ix_ad_experiments_account_id", "ad_experiments")
    op.drop_table("ad_experiments")
