"""Convert unique indexes to unique constraints for ON CONFLICT support.

Migrations 0018 and 0019 created unique indexes (``CREATE UNIQUE INDEX``)
instead of unique constraints (``ALTER TABLE ADD CONSTRAINT ... UNIQUE``).
PostgreSQL's ``ON CONFLICT ON CONSTRAINT <name>`` only recognises named
constraints, not indexes.  This caused the snapshot upsert to crash with:

    constraint "uq_conversion_action_snapshots" does not exist

This migration drops the unique indexes and re-creates them as proper
unique constraints so the upsert logic works correctly.

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-24
"""

from __future__ import annotations

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

# (index_name, table_name, columns)
_TARGETS = [
    (
        "uq_conversion_action_snapshots",
        "conversion_action_snapshots",
        ["account_id", "snapshot_date", "conversion_action_id"],
    ),
    (
        "uq_campaign_extension_snapshots",
        "campaign_extension_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "extension_type"],
    ),
    (
        "uq_sitelink_performance_snapshots",
        "sitelink_performance_snapshots",
        ["account_id", "snapshot_date", "campaign_id", "asset_id"],
    ),
]


def upgrade() -> None:
    for idx_name, table_name, columns in _TARGETS:
        # Drop the unique index (idempotent-ish — Alembic will error if missing).
        op.drop_index(idx_name, table_name=table_name)
        # Re-create as a proper unique constraint.
        op.create_unique_constraint(idx_name, table_name, columns)


def downgrade() -> None:
    for idx_name, table_name, columns in _TARGETS:
        op.drop_constraint(idx_name, table_name, type_="unique")
        op.create_index(idx_name, table_name, columns, unique=True)
