"""Add campaign_resource_name column to launch_briefs.

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_briefs",
        sa.Column(
            "campaign_resource_name",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("launch_briefs", "campaign_resource_name")
