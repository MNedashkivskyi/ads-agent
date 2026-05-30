"""Add website_url column to launch_briefs.

The campaign wizard collects the business website in step 2, but it was
dropped server-side. Persisting it lets us use the real site as the ad
final URL instead of the placeholder ``https://example.com``.

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_briefs",
        sa.Column("website_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_briefs", "website_url")
