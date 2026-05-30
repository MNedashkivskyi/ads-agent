"""Add website_url column to launch_briefs.

NOTE: The application-level feature that *uses* this column was reverted on
this branch (it lives on ``fix/launch-critical-bugs``). This migration is kept
because the deployed database was already stamped at revision ``0056`` by an
earlier deploy — Alembic must be able to locate the revision to boot, and the
sibling feature branch needs the column. The column is nullable and unused by
this branch's ORM model, so leaving it in place is harmless.

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded add so re-running against a database that already has the column
    # (e.g. one stamped at 0056 by an earlier deploy) is a safe no-op.
    op.execute(
        "ALTER TABLE launch_briefs ADD COLUMN IF NOT EXISTS website_url TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE launch_briefs DROP COLUMN IF EXISTS website_url")
