"""Add asset_group_snapshots + listing_group_snapshots (breadth — Shopping/PMax).

Revision ID: 0065
Revises: 0064
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_group_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("asset_group_id", sa.BigInteger, nullable=False),
        sa.Column("campaign_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("ad_strength", sa.String(50), nullable=False, server_default=""),
        sa.Column("primary_status", sa.String(50), nullable=False, server_default=""),
        sa.Column("impressions", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float, nullable=False, server_default="0"),
        sa.Column("conv_value", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "account_id", "snapshot_date", "asset_group_id", name="uq_asset_group_snapshots"
        ),
    )
    op.create_index(
        "ix_asset_group_snapshots_account_date",
        "asset_group_snapshots",
        ["account_id", "snapshot_date"],
    )
    op.create_table(
        "listing_group_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("asset_group_id", sa.BigInteger, nullable=False),
        sa.Column("campaign_id", sa.BigInteger, nullable=False),
        sa.Column("listing_group_id", sa.BigInteger, nullable=False),
        sa.Column("dimension_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("case_value", sa.Text, nullable=False, server_default=""),
        sa.Column("is_catch_all", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "account_id", "snapshot_date", "listing_group_id", name="uq_listing_group_snapshots"
        ),
    )
    op.create_index(
        "ix_listing_group_snapshots_account_date",
        "listing_group_snapshots",
        ["account_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_group_snapshots_account_date", table_name="listing_group_snapshots")
    op.drop_table("listing_group_snapshots")
    op.drop_index("ix_asset_group_snapshots_account_date", table_name="asset_group_snapshots")
    op.drop_table("asset_group_snapshots")
