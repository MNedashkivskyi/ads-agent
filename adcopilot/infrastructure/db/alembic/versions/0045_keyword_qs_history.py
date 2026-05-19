"""Create keyword_qs_history table.

Revision ID: 0045
Revises: 0044
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "keyword_qs_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("criterion_id", sa.BigInteger, nullable=False),
        sa.Column("recorded_date", sa.Date, nullable=False),
        sa.Column("keyword_text", sa.Text, nullable=False),
        sa.Column("match_type", sa.String(50), nullable=False),
        sa.Column("quality_score", sa.Integer, nullable=True),
        sa.Column("expected_ctr", sa.String(50), nullable=True),
        sa.Column("ad_relevance", sa.String(50), nullable=True),
        sa.Column("landing_page_experience", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint(
        "uq_keyword_qs_history_account_criterion_date",
        "keyword_qs_history",
        ["account_id", "criterion_id", "recorded_date"],
    )


def downgrade() -> None:
    op.drop_table("keyword_qs_history")
