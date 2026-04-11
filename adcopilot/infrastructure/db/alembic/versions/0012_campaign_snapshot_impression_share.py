"""Add impression share columns to campaign_snapshots

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "campaign_snapshots",
        sa.Column("search_impression_share", sa.Float(), nullable=True),
    )
    op.add_column(
        "campaign_snapshots",
        sa.Column("search_budget_lost_impression_share", sa.Float(), nullable=True),
    )
    op.add_column(
        "campaign_snapshots",
        sa.Column("search_rank_lost_impression_share", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_snapshots", "search_rank_lost_impression_share")
    op.drop_column("campaign_snapshots", "search_budget_lost_impression_share")
    op.drop_column("campaign_snapshots", "search_impression_share")
