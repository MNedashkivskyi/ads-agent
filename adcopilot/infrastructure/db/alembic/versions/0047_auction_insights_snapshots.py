"""0047 — auction insights snapshots table.

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auction_insights_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("competitor_domain", sa.Text(), nullable=False),
        sa.Column("impression_share", sa.Float(), nullable=True),
        sa.Column("overlap_rate", sa.Float(), nullable=True),
        sa.Column("position_above_rate", sa.Float(), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "account_id", "campaign_id", "competitor_domain", "snapshot_date",
            name="uq_auction_insights_per_day",
        ),
    )
    op.create_index(
        "ix_auction_insights_account_date",
        "auction_insights_snapshots",
        ["account_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_auction_insights_account_date", "auction_insights_snapshots")
    op.drop_table("auction_insights_snapshots")
