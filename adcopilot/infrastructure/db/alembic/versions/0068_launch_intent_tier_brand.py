"""Add intent_tier / is_brand to launch ad groups + intent_tier to keywords.

Persists the brand/non-brand split and per-ad-group search-intent tier so the
proposal preview can show them and downstream tooling can reason about structure.

Revision ID: 0068
Revises: 0067
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_ad_groups",
        sa.Column("intent_tier", sa.String(20), nullable=True),
    )
    op.add_column(
        "launch_ad_groups",
        sa.Column("is_brand", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "launch_keywords",
        sa.Column("intent_tier", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_keywords", "intent_tier")
    op.drop_column("launch_ad_groups", "is_brand")
    op.drop_column("launch_ad_groups", "intent_tier")
