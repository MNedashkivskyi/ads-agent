"""recommendation_snoozes table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-09 02:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_snoozes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recommendation_snoozes_rec_id",
        "recommendation_snoozes",
        ["recommendation_id"],
    )
    op.create_index(
        "ix_recommendation_snoozes_account_id",
        "recommendation_snoozes",
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_snoozes_account_id", table_name="recommendation_snoozes")
    op.drop_index("ix_recommendation_snoozes_rec_id", table_name="recommendation_snoozes")
    op.drop_table("recommendation_snoozes")
