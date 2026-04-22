"""Add seasonal_multiplier and seasonal_vertical to launch_proposals.

Revision ID: 0030
Revises: 0029
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_proposals",
        sa.Column("seasonal_multiplier", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.add_column(
        "launch_proposals",
        sa.Column("seasonal_vertical", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_proposals", "seasonal_vertical")
    op.drop_column("launch_proposals", "seasonal_multiplier")
