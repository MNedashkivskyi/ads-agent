"""0024 — Add launch extension tables (sitelinks, callouts, structured snippets).

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "launch_sitelinks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("launch_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_text", sa.String(25), nullable=False),
        sa.Column("description1", sa.String(35), nullable=False),
        sa.Column("description2", sa.String(35), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_launch_sitelinks_proposal_id", "launch_sitelinks", ["proposal_id"])

    op.create_table(
        "launch_callouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("launch_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(25), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_launch_callouts_proposal_id", "launch_callouts", ["proposal_id"])

    op.create_table(
        "launch_structured_snippets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("launch_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("header", sa.String(100), nullable=False),
        sa.Column(
            "values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_launch_structured_snippets_proposal_id",
        "launch_structured_snippets",
        ["proposal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_launch_structured_snippets_proposal_id", table_name="launch_structured_snippets"
    )
    op.drop_table("launch_structured_snippets")
    op.drop_index("ix_launch_callouts_proposal_id", table_name="launch_callouts")
    op.drop_table("launch_callouts")
    op.drop_index("ix_launch_sitelinks_proposal_id", table_name="launch_sitelinks")
    op.drop_table("launch_sitelinks")
