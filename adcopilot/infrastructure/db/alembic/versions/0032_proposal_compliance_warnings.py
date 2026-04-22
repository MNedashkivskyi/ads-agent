"""Add compliance_warnings JSONB column to launch_proposals.

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "launch_proposals",
        sa.Column("compliance_warnings", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_proposals", "compliance_warnings")
