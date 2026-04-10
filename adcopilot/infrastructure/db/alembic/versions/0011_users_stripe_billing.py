"""Add Stripe billing fields to users

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-10 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'trialing'"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("subscription_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "subscription_id")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_customer_id")
