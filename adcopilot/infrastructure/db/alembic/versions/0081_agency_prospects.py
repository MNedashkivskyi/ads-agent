"""Agency prospecting: agency_prospects table + audit_sessions.agency_org_id (Phase 5C).

Revision ID: 0081
Revises: 0080
Create Date: 2026-06-19
"""

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402

_UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.add_column(
        "audit_sessions",
        sa.Column("agency_org_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_audit_sessions_agency_org_id", "audit_sessions", ["agency_org_id"])

    op.create_table(
        "agency_prospects",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("mcc_customer_id", sa.String(length=50), nullable=True),
        sa.Column("audit_session_id", UUID(as_uuid=True), nullable=True),
        sa.Column("report_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "organization_id", "customer_id", name="uq_agency_prospects_org_customer"
        ),
    )
    op.create_index("ix_agency_prospects_organization_id", "agency_prospects", ["organization_id"])
    op.create_index("ix_agency_prospects_status", "agency_prospects", ["status"])


def downgrade() -> None:
    op.drop_table("agency_prospects")
    op.drop_index("ix_audit_sessions_agency_org_id", table_name="audit_sessions")
    op.drop_column("audit_sessions", "agency_org_id")
