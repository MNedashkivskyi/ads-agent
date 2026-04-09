"""audit_logs table

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-09 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_recommendation_id", "audit_logs", ["recommendation_id"])
    op.create_index("ix_audit_logs_account_id", "audit_logs", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_account_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_recommendation_id", table_name="audit_logs")
    op.drop_table("audit_logs")
