"""0024 — Add acknowledged_at to alerts and create alert_kind_suppressions table.

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add acknowledged_at column to alerts table
    op.add_column(
        "alerts",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create alert_kind_suppressions table
    op.create_table(
        "alert_kind_suppressions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id", "kind", name="uq_alert_kind_suppressions_acct_kind"
        ),
    )
    op.create_index(
        "ix_alert_kind_suppressions_account_id",
        "alert_kind_suppressions",
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_alert_kind_suppressions_account_id",
        table_name="alert_kind_suppressions",
    )
    op.drop_table("alert_kind_suppressions")
    op.drop_column("alerts", "acknowledged_at")
