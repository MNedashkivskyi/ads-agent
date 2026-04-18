"""Create append-only Postgres roles for the audit_logs table.

Revision ID: 0020b
Revises: 0020
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

revision = "0020b"
down_revision = "0020"
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
# Grant/revoke statements kept as named constants so unit tests can
# inspect the SQL text without executing it against a real database.
#
# asyncpg cannot execute multiple statements in one op.execute() call, so
# upgrade() and downgrade() issue each statement individually.
# ---------------------------------------------------------------------------

_APPLY_GRANTS_SQL = (
    "REVOKE ALL ON TABLE audit_logs FROM adept_app;\n"
    "REVOKE ALL ON TABLE audit_logs FROM adept_admin;\n"
    "GRANT SELECT, INSERT ON TABLE audit_logs TO adept_app;\n"
    "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE audit_logs TO adept_admin;"
)

_REVOKE_GRANTS_SQL = (
    "REVOKE ALL ON TABLE audit_logs FROM adept_app;\n"
    "REVOKE ALL ON TABLE audit_logs FROM adept_admin;"
)


def upgrade() -> None:
    op.execute(_CREATE_ROLES_SQL)
    # Revoke stale grants first, then re-apply clean ones.
    # Each statement is a separate execute() — asyncpg forbids multiple
    # commands in a single prepared statement.
    op.execute("REVOKE ALL ON TABLE audit_logs FROM adept_app")
    op.execute("REVOKE ALL ON TABLE audit_logs FROM adept_admin")
    op.execute("GRANT SELECT, INSERT ON TABLE audit_logs TO adept_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE audit_logs TO adept_admin")


def downgrade() -> None:
    # Remove grants but leave the roles in place — dropping a role that is
    # currently the owner of an object or referenced elsewhere would fail,
    # and we don't want a downgrade to block on operator intervention.
    op.execute("REVOKE ALL ON TABLE audit_logs FROM adept_app")
    op.execute("REVOKE ALL ON TABLE audit_logs FROM adept_admin")
