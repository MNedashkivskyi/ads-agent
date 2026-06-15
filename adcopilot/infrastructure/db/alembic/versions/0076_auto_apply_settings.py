"""Auto-apply settings table — Phase 3 / T3.1.

Per-account opt-in for auto-applying low-risk recommendations. Default OFF;
backfills nothing (absence of a row means disabled).

Revision ID: 0076
Revises: 0075
Create Date: 2026-06-16
"""

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402


def upgrade() -> None:
    op.create_table(
        "auto_apply_settings",
        sa.Column("account_id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_risk", sa.String(length=16), nullable=False, server_default="LOW"),
        sa.Column("max_changes_per_day", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("auto_apply_settings")
