"""Static checks for migration 0020 (audit_logs append-only roles).

The integration test that exercises the grants against real Postgres lives
in ``tests/integration/test_audit_log_append_only.py``.  Here we only
validate the migration file's SQL at the text level so mistakes such as
"grant UPDATE to adept_app" are caught in CI without a database.
"""

from __future__ import annotations

import importlib
import re


def _load_migration() -> object:
    return importlib.import_module(
        "adcopilot.infrastructure.db.alembic.versions.0020_audit_log_append_only_roles"
    )


def test_migration_chains_from_0019() -> None:
    # This migration was renumbered to 0020b (from 0020) to resolve a
    # duplicate-revision conflict when two branches both created a 0020
    # migration.  It now sits between 0020 (launch_tables) and 0021.
    mod = _load_migration()
    assert mod.revision == "0020b"  # type: ignore[attr-defined]
    assert mod.down_revision == "0020"  # type: ignore[attr-defined]


def test_migration_creates_both_roles() -> None:
    mod = _load_migration()
    sql = mod._CREATE_ROLES_SQL  # type: ignore[attr-defined]
    assert "CREATE ROLE adept_app" in sql
    assert "CREATE ROLE adept_admin" in sql
    # Both guarded by IF NOT EXISTS pattern
    assert sql.count("rolname = 'adept_app'") == 1
    assert sql.count("rolname = 'adept_admin'") == 1


def test_adept_app_gets_only_select_and_insert() -> None:
    mod = _load_migration()
    sql = mod._APPLY_GRANTS_SQL  # type: ignore[attr-defined]
    # Extract the GRANT statement for adept_app.
    m = re.search(r"GRANT\s+([\w,\s]+?)\s+ON TABLE audit_logs TO adept_app;", sql)
    assert m is not None, "adept_app GRANT not found"
    privs = {p.strip().upper() for p in m.group(1).split(",")}
    assert privs == {"SELECT", "INSERT"}


def test_adept_admin_gets_full_mutation_privileges() -> None:
    mod = _load_migration()
    sql = mod._APPLY_GRANTS_SQL  # type: ignore[attr-defined]
    m = re.search(r"GRANT\s+([\w,\s]+?)\s+ON TABLE audit_logs TO adept_admin;", sql)
    assert m is not None, "adept_admin GRANT not found"
    privs = {p.strip().upper() for p in m.group(1).split(",")}
    assert {"UPDATE", "DELETE"} <= privs
    assert "SELECT" in privs
    assert "INSERT" in privs


def test_revokes_before_granting() -> None:
    """Stale grants from a manual setup must be cleared on upgrade."""
    mod = _load_migration()
    sql = mod._APPLY_GRANTS_SQL  # type: ignore[attr-defined]
    # REVOKE ALL must appear before any GRANT.
    revoke_idx = sql.find("REVOKE ALL")
    grant_idx = sql.find("GRANT")
    assert revoke_idx != -1
    assert grant_idx != -1
    assert revoke_idx < grant_idx


def test_downgrade_does_not_drop_roles() -> None:
    """Dropping roles that own objects fails — keep them on downgrade."""
    mod = _load_migration()
    sql = mod._REVOKE_GRANTS_SQL  # type: ignore[attr-defined]
    assert "DROP ROLE" not in sql.upper()
    assert "REVOKE" in sql
