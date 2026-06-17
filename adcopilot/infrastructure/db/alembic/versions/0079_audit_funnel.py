"""Audit-funnel tables: audit sessions, waste reports, findings, recovery ledger.

Audit Funnel — Phase 0 / Task 0.1.

Revision ID: 0079
Revises: 0078
Create Date: 2026-06-17
"""

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402

_UUID_PK = dict(primary_key=True, server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "audit_sessions",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("google_customer_id", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "oauth_scope", sa.String(length=40), nullable=False, server_default="adwords-readonly"
        ),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="landing"),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", UUID(as_uuid=True), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_audit_sessions_google_customer_id", "audit_sessions", ["google_customer_id"]
    )
    op.create_index("ix_audit_sessions_status", "audit_sessions", ["status"])

    op.create_table(
        "waste_reports",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "audit_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("audit_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="PLN"),
        sa.Column("total_spend_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("headline_waste_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("measurement_gap_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("methodology_version", sa.String(length=20), nullable=False, server_default="1"),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_waste_reports_audit_session_id", "waste_reports", ["audit_session_id"])
    op.create_index("ix_waste_reports_account_id", "waste_reports", ["account_id"])

    op.create_table(
        "waste_findings",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("waste_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column("amount_micros", sa.BigInteger(), nullable=True),
        sa.Column("evidence", JSONB(), nullable=False, server_default="{}"),
        sa.Column("recommendation_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_waste_findings_report_id", "waste_findings", ["report_id"])

    op.create_table(
        "recovery_ledger",
        sa.Column("id", UUID(as_uuid=True), **_UUID_PK),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False),
        sa.Column("finding_id", UUID(as_uuid=True), nullable=True),
        sa.Column("recommendation_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("method", sa.String(length=20), nullable=False, server_default="projected"),
        sa.Column("baseline_metric", JSONB(), nullable=False, server_default="{}"),
        sa.Column("realized_saving_micros", sa.BigInteger(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recovery_ledger_account_id", "recovery_ledger", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_ledger_account_id", table_name="recovery_ledger")
    op.drop_table("recovery_ledger")
    op.drop_index("ix_waste_findings_report_id", table_name="waste_findings")
    op.drop_table("waste_findings")
    op.drop_index("ix_waste_reports_account_id", table_name="waste_reports")
    op.drop_index("ix_waste_reports_audit_session_id", table_name="waste_reports")
    op.drop_table("waste_reports")
    op.drop_index("ix_audit_sessions_status", table_name="audit_sessions")
    op.drop_index("ix_audit_sessions_google_customer_id", table_name="audit_sessions")
    op.drop_table("audit_sessions")
