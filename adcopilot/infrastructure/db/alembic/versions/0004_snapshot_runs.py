"""snapshot runs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-09 00:03:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "snapshot_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("campaigns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ad_groups", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("keywords", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_terms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_snapshot_runs_account_id", "snapshot_runs", ["account_id"])
    op.create_index(
        "ix_snapshot_runs_account_date",
        "snapshot_runs",
        ["account_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_snapshot_runs_account_date", table_name="snapshot_runs")
    op.drop_index("ix_snapshot_runs_account_id", table_name="snapshot_runs")
    op.drop_table("snapshot_runs")
