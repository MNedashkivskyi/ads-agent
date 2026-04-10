"""Add password_hash, notification_hour, language to users

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-10 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "notification_hour",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("9"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "language",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'pl'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "language")
    op.drop_column("users", "notification_hour")
    op.drop_column("users", "password_hash")
