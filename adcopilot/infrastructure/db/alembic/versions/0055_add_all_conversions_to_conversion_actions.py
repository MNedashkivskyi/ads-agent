"""Add all_conversions column to conversion_action_snapshots.

The detection engine checks ``all_conversions > 0`` to determine whether
conversion tracking is working.  Without this column in the DB the
repository could not map it, so ``has_working_tracking`` was always False
and conversion-dependent rules were silently skipped.

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversion_action_snapshots",
        sa.Column("all_conversions", sa.Float, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("conversion_action_snapshots", "all_conversions")
