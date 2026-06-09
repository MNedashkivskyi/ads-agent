"""Enforce one Google Ads account per Adswise user.

A Google Ads customer_id may only be linked to one Adswise user, so the
same Ads account cannot be re-used (e.g. for repeated free trials).
Pre-existing cross-user duplicates are cleaned up first: the earliest
link (the original owner) is kept, later links are removed together with
their stored OAuth credentials.

Revision ID: 0070
Revises: 0069
Create Date: 2026-06-09
"""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None

_DUPLICATE_IDS_SQL = """
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY customer_id
                   ORDER BY connected_at ASC, created_at ASC, id ASC
               ) AS rn
        FROM google_ads_accounts
    ) ranked
    WHERE ranked.rn > 1
"""


def upgrade() -> None:
    op.execute(f"DELETE FROM oauth_credentials WHERE account_id IN ({_DUPLICATE_IDS_SQL})")
    op.execute(f"DELETE FROM google_ads_accounts WHERE id IN ({_DUPLICATE_IDS_SQL})")
    op.create_index(
        "uq_google_ads_accounts_customer_id",
        "google_ads_accounts",
        ["customer_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_google_ads_accounts_customer_id", table_name="google_ads_accounts")
