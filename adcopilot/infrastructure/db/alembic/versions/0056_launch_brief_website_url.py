"""Add website_url column to launch_briefs.

This branch does not use the website_url application feature (it lives on
``fix/launch-critical-bugs``), but the shared database was already stamped at
revision ``0056`` by an earlier deploy. Alembic must be able to locate the
revision to boot, so the script is carried here too. The upgrade is idempotent
(IF NOT EXISTS), making it a safe no-op on the already-migrated database and
still correct on a fresh one. The nullable column is unused by this branch's
ORM model, so leaving it in place is harmless.

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE launch_briefs ADD COLUMN IF NOT EXISTS website_url TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE launch_briefs DROP COLUMN IF EXISTS website_url")
