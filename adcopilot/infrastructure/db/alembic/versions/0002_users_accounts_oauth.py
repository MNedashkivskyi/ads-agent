"""users accounts oauth

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("plan", sa.String(50), nullable=False, server_default="starter"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "google_ads_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(50), nullable=False),
        sa.Column("descriptive_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("currency", sa.String(10), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(100), nullable=False, server_default=""),
        sa.Column("is_manager", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("write_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_google_ads_accounts_user_id", "google_ads_accounts", ["user_id"], unique=False
    )

    op.create_table(
        "oauth_credentials",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(2048), nullable=False),
        sa.Column("access_token_encrypted", sa.String(2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("account_id"),
    )


def downgrade() -> None:
    op.drop_table("oauth_credentials")
    op.drop_index("ix_google_ads_accounts_user_id", table_name="google_ads_accounts")
    op.drop_table("google_ads_accounts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
