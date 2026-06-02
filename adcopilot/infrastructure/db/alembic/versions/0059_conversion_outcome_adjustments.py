"""Add adjustment columns to conversion_outcomes (Phase 2b).

Revision ID: 0059
Revises: 0058
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversion_outcomes", sa.Column("pending_adjustment", sa.String(20), nullable=True)
    )
    op.add_column(
        "conversion_outcomes",
        sa.Column("adjusted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversion_outcomes", "adjusted_at")
    op.drop_column("conversion_outcomes", "pending_adjustment")
