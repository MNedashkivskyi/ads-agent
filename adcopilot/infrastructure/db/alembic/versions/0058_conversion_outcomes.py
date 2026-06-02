"""Add conversion_outcomes and conversion_uploads tables.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversion_outcomes",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("gclid", sa.String(512), nullable=True),
        sa.Column("gbraid", sa.String(512), nullable=True),
        sa.Column("wbraid", sa.String(512), nullable=True),
        sa.Column("hashed_email", sa.String(64), nullable=True),
        sa.Column("hashed_phone", sa.String(64), nullable=True),
        sa.Column("conversion_action_id", sa.BigInteger, nullable=True),
        sa.Column("value", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column("status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("upload_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint(
            "account_id", "external_id", name="uq_conversion_outcomes_account_external"
        ),
    )
    op.create_index(
        "ix_conversion_outcomes_account_status",
        "conversion_outcomes",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_conversion_outcomes_upload",
        "conversion_outcomes",
        ["account_id", "upload_status"],
    )

    op.create_table(
        "conversion_uploads",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("outcome_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("validate_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("succeeded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_conversion_uploads_account_created",
        "conversion_uploads",
        ["account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversion_uploads_account_created", table_name="conversion_uploads")
    op.drop_table("conversion_uploads")
    op.drop_index("ix_conversion_outcomes_upload", table_name="conversion_outcomes")
    op.drop_index("ix_conversion_outcomes_account_status", table_name="conversion_outcomes")
    op.drop_table("conversion_outcomes")
