"""Add avg_monthly_searches to launch_keywords.

Persists the real Keyword Planner search volume attached to a proposal's
keywords (see keyword_enrichment), so it can be shown in the approval preview
and used for reporting. NULL for template/LLM-only keywords (no demand data).

Revision ID: 0066
Revises: 0065
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_keywords",
        sa.Column("avg_monthly_searches", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_keywords", "avg_monthly_searches")
