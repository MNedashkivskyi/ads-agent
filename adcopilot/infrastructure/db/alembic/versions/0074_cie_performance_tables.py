"""CIE shared ingest — shipped keywords, performance facts, search-term proposals.

Revision ID: 0074
Revises: 0073
Create Date: 2026-06-13
"""

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402


def upgrade() -> None:
    op.create_table(
        "cie_shipped_keywords",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.String(32), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column("external_campaign_id", sa.String(32), nullable=True),
        sa.Column("ad_group_id", sa.String(32), nullable=True),
        sa.Column("criterion_id", sa.String(32), nullable=True),
        sa.Column("keyword_text", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(16), nullable=False),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "customer_id", "keyword_text", "ad_group_id", name="uq_cie_shipped_keyword"),
    )
    op.create_index("ix_cie_shipped_keywords_account_id", "cie_shipped_keywords", ["account_id"])
    op.create_index("ix_cie_shipped_keywords_customer_id", "cie_shipped_keywords", ["customer_id"])
    op.create_index("ix_cie_shipped_keyword_text", "cie_shipped_keywords", ["keyword_text"])

    op.create_table(
        "cie_ads_performance_facts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=True),
        sa.Column("value", sa.String(64), nullable=True),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conversions", sa.Float(), server_default="0", nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("performance_label", sa.String(20), nullable=True),
        sa.Column("extra", JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "entity_type", "entity_id", "day", name="uq_cie_perf_fact"),
    )
    op.create_index("ix_cie_perf_fact_account_id", "cie_ads_performance_facts", ["account_id"])
    op.create_index("ix_cie_perf_fact_customer_id", "cie_ads_performance_facts", ["customer_id"])
    op.create_index("ix_cie_perf_fact_day", "cie_ads_performance_facts", ["day"])
    op.create_index("ix_cie_perf_fact_dim", "cie_ads_performance_facts", ["vertical", "dimension", "value"])

    op.create_table(
        "cie_search_term_proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.String(32), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("intent", sa.String(16), nullable=True),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conversions", sa.Float(), server_default="0", nullable=False),
        sa.Column("cost_micros", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("ctr", sa.Float(), server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="proposed", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "term", "kind", name="uq_cie_search_term_proposal"),
    )
    op.create_index("ix_cie_search_term_proposals_account_id", "cie_search_term_proposals", ["account_id"])
    op.create_index("ix_cie_search_term_proposals_customer_id", "cie_search_term_proposals", ["customer_id"])
    op.create_index("ix_cie_search_term_proposal_status", "cie_search_term_proposals", ["account_id", "status"])


def downgrade() -> None:
    for idx in (
        "ix_cie_search_term_proposal_status",
        "ix_cie_search_term_proposals_customer_id",
        "ix_cie_search_term_proposals_account_id",
    ):
        op.drop_index(idx, table_name="cie_search_term_proposals")
    op.drop_table("cie_search_term_proposals")
    for idx in (
        "ix_cie_perf_fact_dim",
        "ix_cie_perf_fact_day",
        "ix_cie_perf_fact_customer_id",
        "ix_cie_perf_fact_account_id",
    ):
        op.drop_index(idx, table_name="cie_ads_performance_facts")
    op.drop_table("cie_ads_performance_facts")
    for idx in (
        "ix_cie_shipped_keyword_text",
        "ix_cie_shipped_keywords_customer_id",
        "ix_cie_shipped_keywords_account_id",
    ):
        op.drop_index(idx, table_name="cie_shipped_keywords")
    op.drop_table("cie_shipped_keywords")
