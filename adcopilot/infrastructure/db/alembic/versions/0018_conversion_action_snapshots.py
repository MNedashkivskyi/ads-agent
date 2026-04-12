"""Create conversion_action_snapshots table.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversion_action_snapshots",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("conversion_action_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(100), nullable=False, server_default=""),
        sa.Column("counting_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "include_in_conversions_metric", sa.Boolean(), nullable=False, server_default="true"
        ),
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
        "uq_conversion_action_snapshots",
        "conversion_action_snapshots",
        ["account_id", "snapshot_date", "conversion_action_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_conversion_action_snapshots", table_name="conversion_action_snapshots")
    op.drop_table("conversion_action_snapshots")
