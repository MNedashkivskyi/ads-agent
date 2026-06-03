"""Add campaign_experiments table (causal measurement).

Revision ID: 0063
Revises: 0062
Create Date: 2026-06-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_experiments",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("account_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("base_campaign_id", sa.BigInteger, nullable=False),
        sa.Column("change_kind", sa.String(32), nullable=False),
        sa.Column("change_payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("traffic_split", sa.Integer, nullable=False, server_default="50"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PROPOSED"),
        sa.Column("draft_resource_name", sa.Text, nullable=True),
        sa.Column("experiment_resource_name", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("control_metrics", JSONB, nullable=False, server_default="{}"),
        sa.Column("treatment_metrics", JSONB, nullable=False, server_default="{}"),
        sa.Column("verdict", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("source_recommendation_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
    )
    op.create_index(
        "ix_campaign_experiments_account_status",
        "campaign_experiments",
        ["account_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_campaign_experiments_account_status", table_name="campaign_experiments")
    op.drop_table("campaign_experiments")
