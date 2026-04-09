"""digest_sent_log table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-09 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_sent_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sent_date", sa.Date(), nullable=False),
        sa.Column("recommendation_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_digest_sent_log_user_id", "digest_sent_log", ["user_id"])
    op.create_index(
        "uq_digest_sent_log_user_date",
        "digest_sent_log",
        ["user_id", "sent_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_digest_sent_log_user_date", table_name="digest_sent_log")
    op.drop_index("ix_digest_sent_log_user_id", table_name="digest_sent_log")
    op.drop_table("digest_sent_log")
