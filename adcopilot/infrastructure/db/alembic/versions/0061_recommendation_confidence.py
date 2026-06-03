"""Add confidence column to recommendations (Smart Bidding modernization B).

Revision ID: 0061
Revises: 0060
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("confidence", sa.String(20), nullable=False, server_default="MEDIUM"),
    )


def downgrade() -> None:
    op.drop_column("recommendations", "confidence")
