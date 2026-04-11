"""Add ad_strength column to ad_snapshots

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-11 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ad_snapshots",
        sa.Column("ad_strength", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ad_snapshots", "ad_strength")
