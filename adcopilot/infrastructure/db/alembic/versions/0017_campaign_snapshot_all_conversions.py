"""Add all_conversions to campaign_snapshots.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaign_snapshots",
        sa.Column("all_conversions", sa.Float(), nullable=False, server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_column("campaign_snapshots", "all_conversions")
