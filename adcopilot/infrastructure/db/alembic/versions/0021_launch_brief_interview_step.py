"""Add interview_step column to launch_briefs.

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_briefs",
        sa.Column(
            "interview_step",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("launch_briefs", "interview_step")
