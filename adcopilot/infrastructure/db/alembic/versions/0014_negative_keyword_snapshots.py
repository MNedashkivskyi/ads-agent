"""Add negative_keyword_snapshots table

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-12 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "negative_keyword_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("criterion_id", sa.BigInteger(), nullable=False),
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "ad_group_id", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("match_type", sa.String(50), nullable=False, server_default=""),
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
    )
    op.create_index(
        "ix_negative_keyword_snapshots_account_id",
        "negative_keyword_snapshots",
        ["account_id"],
    )
    op.create_unique_constraint(
        "uq_negative_keyword_snapshots",
        "negative_keyword_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "ad_group_id", "criterion_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_negative_keyword_snapshots", "negative_keyword_snapshots", type_="unique"
    )
    op.drop_index(
        "ix_negative_keyword_snapshots_account_id",
        table_name="negative_keyword_snapshots",
    )
    op.drop_table("negative_keyword_snapshots")
