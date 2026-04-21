"""0026 — Add recommendation performance baselines and comparisons tables.

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_performance_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.BigInteger, nullable=False),
        sa.Column("baseline_date", sa.Date, nullable=False),
        sa.Column("cost_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("impressions", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float, nullable=False, server_default="0"),
        sa.Column("conv_value", sa.Float, nullable=False, server_default="0"),
        sa.Column("cpa_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float, nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_perf_baselines_rec_id", "recommendation_performance_baselines", ["recommendation_id"])
    op.create_index("ix_perf_baselines_account_id", "recommendation_performance_baselines", ["account_id"])

    op.create_table(
        "recommendation_performance_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comparison_window_days", sa.Integer, nullable=False),
        sa.Column("current_cost_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_clicks", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_impressions", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("current_conversions", sa.Float, nullable=False, server_default="0"),
        sa.Column("current_cpa_micros", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("delta_cpa_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("delta_conversions_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("delta_ctr_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("compared_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["baseline_id"], ["recommendation_performance_baselines.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("recommendation_id", "comparison_window_days", name="uq_comparison_rec_window"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_perf_comparisons_rec_id", "recommendation_performance_comparisons", ["recommendation_id"]
    )


def downgrade() -> None:
    op.drop_table("recommendation_performance_comparisons")
    op.drop_table("recommendation_performance_baselines")
