"""Create campaign_extension_snapshots and sitelink_performance_snapshots tables.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_extension_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("extension_type", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_campaign_extension_snapshots",
        "campaign_extension_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "extension_type"],
        unique=True,
    )

    op.create_table(
        "sitelink_performance_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_sitelink_performance_snapshots",
        "sitelink_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "asset_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_sitelink_performance_snapshots", table_name="sitelink_performance_snapshots")
    op.drop_table("sitelink_performance_snapshots")
    op.drop_index("uq_campaign_extension_snapshots", table_name="campaign_extension_snapshots")
    op.drop_table("campaign_extension_snapshots")
