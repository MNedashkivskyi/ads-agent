"""Add organization_id to google_ads_accounts + backfill from the owner's personal org.

Phase 5B — org-owned accounts (additive foundation). The column is nullable for
the rollout: new accounts set it to the owner's personal org and existing rows are
backfilled here. Access control flips to org-membership in a follow-up.

Revision ID: 0080
Revises: 0079
Create Date: 2026-06-18
"""

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402


def upgrade() -> None:
    op.add_column(
        "google_ads_accounts",
        sa.Column("organization_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_google_ads_accounts_organization_id",
        "google_ads_accounts",
        ["organization_id"],
    )
    # Backfill each account's org from its owner's personal org (created in 0078).
    # owner_user_id is stored as text; google_ads_accounts.user_id is a UUID.
    op.execute(
        """
        UPDATE google_ads_accounts AS a
        SET organization_id = o.id
        FROM organizations AS o
        WHERE o.owner_user_id = a.user_id::text
          AND o.is_personal = true
          AND a.organization_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_google_ads_accounts_organization_id", table_name="google_ads_accounts")
    op.drop_column("google_ads_accounts", "organization_id")
