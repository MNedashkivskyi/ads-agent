"""Add vertical column to launch_briefs.

Revision ID: 0031
Revises: 0030
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_briefs",
        sa.Column("vertical", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_briefs", "vertical")
