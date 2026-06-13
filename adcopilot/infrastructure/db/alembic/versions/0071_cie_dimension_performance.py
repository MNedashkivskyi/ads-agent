"""Campaign Intelligence Engine — shared learning spine table.

Creates ``cie_dimension_performance``: learned weights per
(vertical, dimension, value, language) for both the keyword-intent and
creative-angle tracks.

Revision ID: 0071
Revises: 0070
Create Date: 2026-06-13
"""

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402


def upgrade() -> None:
    op.create_table(
        "cie_dimension_performance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vertical", sa.String(64), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("sample_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conversions", sa.Float(), server_default="0", nullable=False),
        sa.Column("weighted_ctr", sa.Float(), server_default="0", nullable=False),
        sa.Column("weighted_conv", sa.Float(), server_default="0", nullable=False),
        sa.Column("smoothed_score", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vertical", "dimension", "value", "language",
            name="uq_cie_dimension_performance_key",
        ),
    )
    op.create_index(
        "ix_cie_dimperf_vertical_dimension",
        "cie_dimension_performance",
        ["vertical", "dimension"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cie_dimperf_vertical_dimension", table_name="cie_dimension_performance"
    )
    op.drop_table("cie_dimension_performance")
