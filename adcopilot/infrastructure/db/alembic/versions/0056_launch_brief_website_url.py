"""Add website_url column to launch_briefs.

The shared database was stamped at revision ``0056`` by an earlier deploy of
the website_url feature. To keep every branch cut from ``master`` aligned with
the live database (and able to boot), this idempotent migration is carried on
``master`` as the canonical 0056.

The upgrade uses ``ADD COLUMN IF NOT EXISTS`` so it is a safe no-op on the
already-migrated database and correct on a fresh one. The column is nullable
and unused by code on branches that have not adopted the website_url feature.

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
