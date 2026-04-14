"""Create append-only Postgres roles for the audit_logs table.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-14

Two roles are created and granted minimum-necessary privileges on the
``audit_logs`` table:

* ``adept_app``   — the role the application should connect as at runtime.
                    Has ``SELECT`` + ``INSERT`` only.  Any ``UPDATE`` or
                    ``DELETE`` issued by the app will fail with a
                    ``permission denied`` error from Postgres, making the
                    table append-only *at the database level* regardless
                    of bugs in the ORM layer.

* ``adept_admin`` — the role migrations and operator-level scripts
                    connect as.  Has full read/write privileges so
                    schema changes and one-off corrections remain
                    possible.  In production, the DATABASE_URL used by
                    the API and worker containers should reference
                    ``adept_app``; the URL used by the
                    migration/deploy job should reference
                    ``adept_admin``.

Idempotent: uses ``CREATE ROLE ... IF NOT EXISTS``-style guards so
re-runs (e.g. after a restore) do not fail.  ``NOLOGIN`` is the default;
operators assign passwords out-of-band via ``ALTER ROLE ... LOGIN
PASSWORD '...'``.
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Role creation is wrapped in a DO block because Postgres has no
# CREATE ROLE IF NOT EXISTS until v15, and we still support v14.
# ---------------------------------------------------------------------------

_CREATE_ROLES_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'adept_app') THEN
        CREATE ROLE adept_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'adept_admin') THEN
        CREATE ROLE adept_admin NOLOGIN;
    END IF;
END
$$;
"""

# ---------------------------------------------------------------------------
# Revoke everything first, then grant only what each role needs.  This
# protects against stale grants from an earlier manual setup.
# ---------------------------------------------------------------------------

_APPLY_GRANTS_SQL = """
REVOKE ALL ON TABLE audit_logs FROM adept_app;
REVOKE ALL ON TABLE audit_logs FROM adept_admin;

-- adept_app: append-only.  SELECT is included so the API can show users
-- their own history.  No UPDATE, no DELETE, no TRUNCATE.
GRANT SELECT, INSERT ON TABLE audit_logs TO adept_app;

-- adept_admin: full privileges for migrations and manual corrections.
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE audit_logs TO adept_admin;
"""

_REVOKE_GRANTS_SQL = """
REVOKE ALL ON TABLE audit_logs FROM adept_app;
REVOKE ALL ON TABLE audit_logs FROM adept_admin;
"""


def upgrade() -> None:
    op.execute(_CREATE_ROLES_SQL)
    op.execute(_APPLY_GRANTS_SQL)


def downgrade() -> None:
    # Remove grants but leave the roles in place — dropping a role that is
    # currently the owner of an object or referenced elsewhere would fail,
    # and we don't want a downgrade to block on operator intervention.
    op.execute(_REVOKE_GRANTS_SQL)
