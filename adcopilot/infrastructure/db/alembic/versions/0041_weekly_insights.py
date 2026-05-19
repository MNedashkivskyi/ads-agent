"""Create weekly_insights table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_insights",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("insight_text", sa.Text(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_weekly_insights_user_id", "weekly_insights", ["user_id"])
    op.create_index("ix_weekly_insights_week_start", "weekly_insights", ["week_start"])


def downgrade() -> None:
    op.drop_index("ix_weekly_insights_week_start", "weekly_insights")
    op.drop_index("ix_weekly_insights_user_id", "weekly_insights")
    op.drop_table("weekly_insights")
