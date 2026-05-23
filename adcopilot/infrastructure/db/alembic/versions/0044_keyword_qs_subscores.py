"""Add QS sub-score columns to keyword_snapshots.

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("keyword_snapshots", sa.Column("expected_ctr", sa.String(50), nullable=True))
    op.add_column("keyword_snapshots", sa.Column("ad_relevance", sa.String(50), nullable=True))
    op.add_column(
        "keyword_snapshots", sa.Column("landing_page_experience", sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("keyword_snapshots", "landing_page_experience")
    op.drop_column("keyword_snapshots", "ad_relevance")
    op.drop_column("keyword_snapshots", "expected_ctr")
