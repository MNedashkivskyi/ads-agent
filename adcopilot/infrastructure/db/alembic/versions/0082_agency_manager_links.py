"""Agency MCC link: agency_manager_links table (Phase 5C-2).

Stores an agency org's connected Google Ads manager (MCC) account + its read-only
refresh token (encrypted at rest). One MCC per org in v1.

Revision ID: 0082
Revises: 0081
Create Date: 2026-06-19
"""

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402

_UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "agency_manager_links",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("mcc_customer_id", sa.String(length=50), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(length=2048), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", name="uq_agency_manager_links_org"),
    )
    op.create_index(
        "ix_agency_manager_links_organization_id", "agency_manager_links", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_table("agency_manager_links")
