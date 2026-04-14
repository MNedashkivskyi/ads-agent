"""Verify at the database level that migration 0020 makes audit_logs
append-only for the ``adept_app`` role.

The test connects as superuser, runs the grant SQL from the migration,
creates a scratch ``adept_app_test_user`` that inherits from the
``adept_app`` role, then opens a second connection using that user and
confirms:

  * SELECT and INSERT succeed
  * UPDATE, DELETE, and TRUNCATE are denied with Postgres
    ``insufficient_privilege`` (SQLSTATE 42501)

Marked as integration because it needs a real Postgres with superuser
rights on the test database.
"""

from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.sql import text

from tests.conftest import get_test_db_url

# The migration module name begins with a digit and is not importable via
# the normal ``from X import Y`` syntax, so we load it dynamically.
_migration_module = importlib.import_module(
    "adcopilot.infrastructure.db.alembic.versions.0020_audit_log_append_only_roles"
)

_TEST_ROLE = "adept_app_test_user"
_TEST_PASSWORD = "scratch-password-for-tests"  # test-only constant


def _role_url(base_url: str) -> str:
    """Swap the credentials in the test DB URL for the scratch role."""
    # base_url is postgresql+asyncpg://user:pass@host:port/dbname — just
    # rebuild with _TEST_ROLE's credentials.
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(base_url)
    new_netloc = f"{_TEST_ROLE}:{_TEST_PASSWORD}@{parsed.hostname}"
    if parsed.port:
        new_netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=new_netloc))


@pytest.mark.integration
async def test_adept_app_cannot_mutate_audit_logs(db_session: AsyncSession) -> None:
    """As ``adept_app``: INSERT/SELECT work; UPDATE/DELETE/TRUNCATE error."""
    # 1. Apply the migration's SQL inside the current superuser session.
    await db_session.execute(text(_migration_module._CREATE_ROLES_SQL))
    await db_session.execute(text(_migration_module._APPLY_GRANTS_SQL))

    # 2. Create a login user that inherits from adept_app so we can actually
    #    connect as the role.  Clean up any leftover from a previous run.
    await db_session.execute(text(f"DROP ROLE IF EXISTS {_TEST_ROLE}"))
    await db_session.execute(
        text(
            f"CREATE ROLE {_TEST_ROLE} LOGIN PASSWORD :pw IN ROLE adept_app"
        ).bindparams(pw=_TEST_PASSWORD)
    )
    await db_session.commit()

    # Seed one row as superuser so UPDATE/DELETE have something to target.
    row_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO audit_logs (id, account_id, kind, action, payload, created_at) "
            "VALUES (:id, :acc, 'test', 'test', '{}'::jsonb, now())"
        ).bindparams(id=row_id, acc=uuid.uuid4())
    )
    await db_session.commit()

    # 3. Open a new engine/session as adept_app_test_user.
    app_engine = create_async_engine(_role_url(get_test_db_url()))
    try:
        async with AsyncSession(app_engine) as app_session:
            # SELECT — allowed.
            result = await app_session.execute(
                text("SELECT COUNT(*) FROM audit_logs WHERE id = :id").bindparams(
                    id=row_id
                )
            )
            assert result.scalar_one() == 1

            # INSERT — allowed.
            await app_session.execute(
                text(
                    "INSERT INTO audit_logs (id, account_id, kind, action, payload, created_at) "
                    "VALUES (:id, :acc, 'from-app', 'ok', '{}'::jsonb, now())"
                ).bindparams(id=uuid.uuid4(), acc=uuid.uuid4())
            )
            await app_session.commit()

            # UPDATE — denied.
            with pytest.raises(ProgrammingError) as update_exc:
                await app_session.execute(
                    text("UPDATE audit_logs SET action = 'tamper' WHERE id = :id").bindparams(
                        id=row_id
                    )
                )
                await app_session.commit()
            assert "permission denied" in str(update_exc.value).lower()
            await app_session.rollback()

            # DELETE — denied.
            with pytest.raises(ProgrammingError) as delete_exc:
                await app_session.execute(
                    text("DELETE FROM audit_logs WHERE id = :id").bindparams(id=row_id)
                )
                await app_session.commit()
            assert "permission denied" in str(delete_exc.value).lower()
            await app_session.rollback()

            # TRUNCATE — denied.
            with pytest.raises(ProgrammingError) as truncate_exc:
                await app_session.execute(text("TRUNCATE TABLE audit_logs"))
                await app_session.commit()
            assert "permission denied" in str(truncate_exc.value).lower()
            await app_session.rollback()
    finally:
        await app_engine.dispose()
        # Drop the scratch role so the test is idempotent.
        await db_session.execute(text(f"DROP ROLE IF EXISTS {_TEST_ROLE}"))
        await db_session.commit()
