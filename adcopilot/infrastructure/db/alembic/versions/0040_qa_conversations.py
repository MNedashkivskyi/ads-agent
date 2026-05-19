"""Create qa_conversations table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qa_conversations_user_id", "qa_conversations", ["user_id"])
    op.create_index("ix_qa_conversations_created_at", "qa_conversations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_qa_conversations_created_at", "qa_conversations")
    op.drop_index("ix_qa_conversations_user_id", "qa_conversations")
    op.drop_table("qa_conversations")
