"""Create prompt_versions table for versioned LLM prompt storage.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("prompt_key", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_prompt_versions_key_version",
        "prompt_versions",
        ["prompt_key", "version"],
    )
    op.create_index(
        "ix_prompt_versions_prompt_key",
        "prompt_versions",
        ["prompt_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_versions_prompt_key", table_name="prompt_versions")
    op.drop_constraint("uq_prompt_versions_key_version", "prompt_versions")
    op.drop_table("prompt_versions")
