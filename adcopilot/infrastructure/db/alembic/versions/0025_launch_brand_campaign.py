"""0025 — Add brand campaign fields to launch_proposals.

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_proposals",
        sa.Column("brand_campaign_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "launch_proposals",
        sa.Column(
            "brand_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "launch_proposals",
        sa.Column("brand_daily_budget_micros", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "launch_proposals",
        sa.Column(
            "brand_ad",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("launch_proposals", "brand_ad")
    op.drop_column("launch_proposals", "brand_daily_budget_micros")
    op.drop_column("launch_proposals", "brand_keywords")
    op.drop_column("launch_proposals", "brand_campaign_name")
