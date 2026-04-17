"""Add target_cpa_micros to campaign_snapshots.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaign_snapshots",
        sa.Column("target_cpa_micros", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_snapshots", "target_cpa_micros")
