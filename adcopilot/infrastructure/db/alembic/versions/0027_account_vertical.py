"""Add vertical classification columns to google_ads_accounts.

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "google_ads_accounts",
        sa.Column("vertical", sa.String(50), nullable=True),
    )
    op.add_column(
        "google_ads_accounts",
        sa.Column("sub_vertical", sa.String(100), nullable=True),
    )
    op.add_column(
        "google_ads_accounts",
        sa.Column(
            "vertical_classified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_google_ads_accounts_vertical",
        "google_ads_accounts",
        ["vertical"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_google_ads_accounts_vertical", table_name="google_ads_accounts")
    op.drop_column("google_ads_accounts", "vertical_classified_at")
    op.drop_column("google_ads_accounts", "sub_vertical")
    op.drop_column("google_ads_accounts", "vertical")
