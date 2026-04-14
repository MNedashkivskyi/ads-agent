"""Create launch_briefs, launch_proposals, launch_ad_groups, launch_keywords, launch_ads.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── launch_briefs ─────────────────────────────────────────────────────────
    op.create_table(
        "launch_briefs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("business_description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column(
            "typical_customer_value",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column("primary_action", sa.String(255), nullable=False),
        sa.Column(
            "monthly_budget_pln",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
        ),
        sa.Column(
            "exclusions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("language", sa.String(10), nullable=False, server_default="pl"),
        sa.Column("status", sa.String(30), nullable=False),
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
    op.create_index("ix_launch_briefs_user_id", "launch_briefs", ["user_id"])
    op.create_index("ix_launch_briefs_account_id", "launch_briefs", ["account_id"])
    op.create_index("ix_launch_briefs_status", "launch_briefs", ["status"])

    # ── launch_proposals ─────────────────────────────────────────────────────
    op.create_table(
        "launch_proposals",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "brief_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("launch_briefs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("campaign_name", sa.String(255), nullable=False),
        sa.Column("daily_budget_micros", sa.BigInteger(), nullable=False),
        sa.Column("location_targeting", sa.String(255), nullable=False),
        sa.Column("bidding_strategy", sa.String(100), nullable=False),
        sa.Column(
            "negative_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "estimated_cpc_min_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "estimated_cpc_max_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
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
    op.create_index("ix_launch_proposals_brief_id", "launch_proposals", ["brief_id"])

    # ── launch_ad_groups ─────────────────────────────────────────────────────
    op.create_table(
        "launch_ad_groups",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("launch_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_launch_ad_groups_proposal_id", "launch_ad_groups", ["proposal_id"])

    # ── launch_keywords ──────────────────────────────────────────────────────
    op.create_table(
        "launch_keywords",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ad_group_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("launch_ad_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column(
            "estimated_cpc_micros",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_launch_keywords_ad_group_id", "launch_keywords", ["ad_group_id"])

    # ── launch_ads ───────────────────────────────────────────────────────────
    op.create_table(
        "launch_ads",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ad_group_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("launch_ad_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "headlines",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "descriptions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("path1", sa.String(15), nullable=False, server_default=""),
        sa.Column("path2", sa.String(15), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_launch_ads_ad_group_id", "launch_ads", ["ad_group_id"])


def downgrade() -> None:
    op.drop_table("launch_ads")
    op.drop_table("launch_keywords")
    op.drop_table("launch_ad_groups")
    op.drop_table("launch_proposals")
    op.drop_table("launch_briefs")
