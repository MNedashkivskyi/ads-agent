"""Add vertical_benchmark_snapshots table.

Revision ID: 0029
Revises: 0028
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0029"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vertical_benchmark_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("vertical", sa.String(50), nullable=False),
        sa.Column("city_tier", sa.Integer, nullable=False),
        sa.Column("snapshot_week", sa.Date, nullable=False),
        sa.Column("account_count", sa.Integer, nullable=False),
        sa.Column("avg_cpa_micros", sa.BigInteger, nullable=False),
        sa.Column("median_cpa_micros", sa.BigInteger, nullable=False),
        sa.Column("p25_cpa_micros", sa.BigInteger, nullable=False),
        sa.Column("p75_cpa_micros", sa.BigInteger, nullable=False),
        sa.Column("avg_ctr", sa.Float, nullable=False),
        sa.Column("avg_conversion_rate", sa.Float, nullable=False),
        sa.Column("avg_monthly_spend_micros", sa.BigInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_vbs_vertical", "vertical_benchmark_snapshots", ["vertical"])
    op.create_index("ix_vbs_snapshot_week", "vertical_benchmark_snapshots", ["snapshot_week"])
    op.create_index(
        "ix_vbs_vertical_tier_week",
        "vertical_benchmark_snapshots",
        ["vertical", "city_tier", "snapshot_week"],
    )


def downgrade() -> None:
    op.drop_index("ix_vbs_vertical_tier_week", table_name="vertical_benchmark_snapshots")
    op.drop_index("ix_vbs_snapshot_week", table_name="vertical_benchmark_snapshots")
    op.drop_index("ix_vbs_vertical", table_name="vertical_benchmark_snapshots")
    op.drop_table("vertical_benchmark_snapshots")
