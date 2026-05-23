"""Add targeting performance snapshot tables (device, geo, hour, day_of_week, audience)

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-12 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- device_performance_snapshots ---
    op.create_table(
        "device_performance_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("device", sa.String(50), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_device_performance_snapshots_account_id", "device_performance_snapshots", ["account_id"]
    )
    op.create_unique_constraint(
        "uq_device_performance_snapshots",
        "device_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "device"],
    )

    # --- geo_performance_snapshots ---
    op.create_table(
        "geo_performance_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_geo_performance_snapshots_account_id", "geo_performance_snapshots", ["account_id"]
    )
    op.create_unique_constraint(
        "uq_geo_performance_snapshots",
        "geo_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "location_id"],
    )

    # --- hour_performance_snapshots ---
    op.create_table(
        "hour_performance_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("hour_of_day", sa.Integer(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hour_performance_snapshots_account_id", "hour_performance_snapshots", ["account_id"]
    )
    op.create_unique_constraint(
        "uq_hour_performance_snapshots",
        "hour_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "hour_of_day"],
    )

    # --- day_of_week_performance_snapshots ---
    op.create_table(
        "day_of_week_performance_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("day_of_week", sa.String(20), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_day_of_week_performance_snapshots_account_id",
        "day_of_week_performance_snapshots",
        ["account_id"],
    )
    op.create_unique_constraint(
        "uq_day_of_week_performance_snapshots",
        "day_of_week_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "day_of_week"],
    )

    # --- audience_performance_snapshots ---
    op.create_table(
        "audience_performance_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=False),
        sa.Column("criterion_id", sa.BigInteger(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audience_performance_snapshots_account_id",
        "audience_performance_snapshots",
        ["account_id"],
    )
    op.create_unique_constraint(
        "uq_audience_performance_snapshots",
        "audience_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "ad_group_id", "criterion_id"],
    )


def downgrade() -> None:
    for table in (
        "audience_performance_snapshots",
        "day_of_week_performance_snapshots",
        "hour_performance_snapshots",
        "geo_performance_snapshots",
        "device_performance_snapshots",
    ):
        op.drop_constraint(f"uq_{table}", table, type_="unique")
        op.drop_index(f"ix_{table}_account_id", table_name=table)
        op.drop_table(table)
