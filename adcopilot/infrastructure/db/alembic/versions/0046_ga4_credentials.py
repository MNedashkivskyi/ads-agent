"""Add GA4 credentials and ga4_page_snapshots tables.

Revision ID: 0046
Revises: 0045
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ga4_credentials",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, unique=True, index=True),
        sa.Column("property_id", sa.String(64), nullable=False),
        sa.Column("refresh_token_enc", sa.Text, nullable=False),
        sa.Column("access_token_enc", sa.Text, nullable=True),
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
    )

    op.create_table(
        "ga4_page_snapshots",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("page_path", sa.Text, nullable=False),
        sa.Column("sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bounce_rate", sa.Float, nullable=True),
        sa.Column("avg_session_duration_sec", sa.Float, nullable=True),
        sa.Column("pages_per_session", sa.Float, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_ga4_page_snapshots_account_date_path",
        "ga4_page_snapshots",
        ["account_id", "snapshot_date", "page_path"],
    )


def downgrade() -> None:
    op.drop_table("ga4_page_snapshots")
    op.drop_table("ga4_credentials")
