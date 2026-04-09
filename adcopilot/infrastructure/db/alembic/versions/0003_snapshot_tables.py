"""snapshot tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-09 00:02:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add needs_reauth to google_ads_accounts
    op.add_column(
        "google_ads_accounts",
        sa.Column("needs_reauth", sa.Boolean(), nullable=False, server_default="false"),
    )

    # campaign_snapshots
    op.create_table(
        "campaign_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("channel_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("budget_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bidding_strategy", sa.String(100), nullable=False, server_default=""),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
        sa.Column("conv_value", sa.Float(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("account_id", "snapshot_date", "campaign_id",
                            name="uq_campaign_snapshots"),
    )
    op.create_index("ix_campaign_snapshots_account_date",
                    "campaign_snapshots", ["account_id", "snapshot_date"])
    op.create_index("ix_campaign_snapshots_account_campaign",
                    "campaign_snapshots", ["account_id", "campaign_id"])

    # ad_group_snapshots
    op.create_table(
        "ad_group_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("account_id", "snapshot_date", "ad_group_id",
                            name="uq_ad_group_snapshots"),
    )
    op.create_index("ix_ad_group_snapshots_account_date",
                    "ad_group_snapshots", ["account_id", "snapshot_date"])

    # keyword_snapshots
    op.create_table(
        "keyword_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("criterion_id", sa.BigInteger(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("match_type", sa.String(50), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_cpc_micros", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("account_id", "snapshot_date", "criterion_id", "ad_group_id",
                            name="uq_keyword_snapshots"),
    )
    op.create_index("ix_keyword_snapshots_account_date",
                    "keyword_snapshots", ["account_id", "snapshot_date"])

    # search_term_snapshots
    op.create_table(
        "search_term_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("search_term", sa.Text(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
        sa.Column("matched_keyword_id", sa.BigInteger(), nullable=True),
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
        sa.UniqueConstraint("account_id", "snapshot_date", "search_term", "ad_group_id",
                            name="uq_search_term_snapshots"),
    )
    op.create_index("ix_search_term_snapshots_account_date",
                    "search_term_snapshots", ["account_id", "snapshot_date"])
    op.create_index("ix_search_term_snapshots_account_date_term",
                    "search_term_snapshots", ["account_id", "snapshot_date", "search_term"])

    # ad_snapshots
    op.create_table(
        "ad_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("ad_id", sa.BigInteger(), nullable=False),
        sa.Column("ad_group_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(100), nullable=False, server_default=""),
        sa.Column("status", sa.String(50), nullable=False, server_default=""),
        sa.Column("headlines_json", postgresql.JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("descriptions_json", postgresql.JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("final_urls_json", postgresql.JSONB(), nullable=False, server_default="'[]'"),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Float(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("account_id", "snapshot_date", "ad_id",
                            name="uq_ad_snapshots"),
    )
    op.create_index("ix_ad_snapshots_account_date",
                    "ad_snapshots", ["account_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_table("ad_snapshots")
    op.drop_table("search_term_snapshots")
    op.drop_table("keyword_snapshots")
    op.drop_table("ad_group_snapshots")
    op.drop_table("campaign_snapshots")
    op.drop_column("google_ads_accounts", "needs_reauth")
