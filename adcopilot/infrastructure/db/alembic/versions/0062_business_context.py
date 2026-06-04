"""Add business-context columns to business_economics (onboarding).

Revision ID: 0062
Revises: 0061
Create Date: 2026-06-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("business_economics", sa.Column("primary_goal", sa.String(20), nullable=True))
    op.add_column("business_economics", sa.Column("target_cpa", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "business_economics",
        sa.Column("monthly_conversion_capacity", sa.Integer, nullable=True),
    )
    op.add_column(
        "business_economics",
        sa.Column("brand_terms", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "business_economics",
        sa.Column("excluded_terms", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("business_economics", "excluded_terms")
    op.drop_column("business_economics", "brand_terms")
    op.drop_column("business_economics", "monthly_conversion_capacity")
    op.drop_column("business_economics", "target_cpa")
    op.drop_column("business_economics", "primary_goal")
