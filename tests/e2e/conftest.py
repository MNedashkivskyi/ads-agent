"""Fixtures for end-to-end tests.

Spins up isolated Postgres + Redis for the test session.  Two strategies are
supported:

1. **testcontainers** (default): the test starts fresh Postgres and Redis
   containers via Docker.  This is the preferred mode — it guarantees the
   test runs against a clean, isolated stack every time.

2. **External services** (CI / local with docker-compose):  if the
   ``TEST_E2E_DATABASE_URL`` and ``TEST_E2E_REDIS_URL`` environment
   variables are set, the fixtures use those instead of starting containers.
   CI uses this path via GitHub Actions service containers for faster runs.

Either way, the Postgres schema is created by running the full Alembic
migration chain against an empty database — this guarantees the named unique
constraints required by the upsert logic (``ON CONFLICT ON CONSTRAINT``) exist,
which ``Base.metadata.create_all`` alone does not produce.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Tables that must be truncated between tests to keep runs deterministic.
# Listed in FK-safe order (though TRUNCATE ... CASCADE handles this anyway).
_TRUNCATE_TABLES = (
    "audit_logs",
    "recommendation_snoozes",
    "recommendations",
    "digest_sent_log",
    "snapshot_runs",
    "sitelink_performance_snapshots",
    "campaign_extension_snapshots",
    "conversion_action_snapshots",
    "audience_performance_snapshots",
    "day_of_week_performance_snapshots",
    "hour_performance_snapshots",
    "geo_performance_snapshots",
    "device_performance_snapshots",
    "negative_keyword_snapshots",
    "ad_snapshots",
    "search_term_snapshots",
    "keyword_snapshots",
    "ad_group_snapshots",
    "campaign_snapshots",
    "oauth_credentials",
    "google_ads_accounts",
    "users",
)


def _env_database_url() -> str | None:
    return os.environ.get("TEST_E2E_DATABASE_URL")


def _env_redis_url() -> str | None:
    return os.environ.get("TEST_E2E_REDIS_URL")


def _to_asyncpg(url: str) -> str:
    """Normalise a sync postgres URL to asyncpg if needed."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def _to_sync(url: str) -> str:
    """Convert an asyncpg URL back to the psycopg2/psycopg default (Alembic uses psycopg via asyncpg plugin)."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    """Yield an asyncpg URL for a clean Postgres instance.

    If ``TEST_E2E_DATABASE_URL`` is set, use it directly (CI path).  Otherwise
    start a disposable Postgres container via testcontainers.  The test is
    skipped if neither option is available.
    """
    env_url = _env_database_url()
    if env_url:
        yield _to_asyncpg(env_url)
        return

    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip(
            "E2E tests require either TEST_E2E_DATABASE_URL env var or "
            "the `testcontainers` package to be installed."
        )

    container = PostgresContainer("postgres:16-alpine")
    try:
        container.start()
    except Exception as exc:  # Docker not available / daemon not running
        pytest.skip(f"Could not start Postgres testcontainer: {exc}")

    try:
        url = container.get_connection_url()
        yield _to_asyncpg(url)
    finally:
        container.stop()


@pytest.fixture(scope="session")
def redis_url() -> Generator[str, None, None]:
    """Yield a Redis URL for a clean Redis instance."""
    env_url = _env_redis_url()
    if env_url:
        yield env_url
        return

    try:
        from testcontainers.redis import RedisContainer  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip(
            "E2E tests require either TEST_E2E_REDIS_URL env var or "
            "the `testcontainers` package to be installed."
        )

    container = RedisContainer("redis:7-alpine")
    try:
        container.start()
    except Exception as exc:
        pytest.skip(f"Could not start Redis testcontainer: {exc}")

    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest.fixture(scope="session")
def e2e_env(postgres_url: str, redis_url: str) -> Generator[dict[str, str], None, None]:
    """Export DATABASE_URL / REDIS_URL / secrets into the process environment.

    We intentionally mutate ``os.environ`` so any nested ``Settings()`` (or
    cached ``get_settings()``) picks up the test URLs.  The real values are
    restored on teardown.
    """
    original: dict[str, str | None] = {}
    env_patch: dict[str, str] = {
        "DATABASE_URL": postgres_url,
        "REDIS_URL": redis_url,
        "SECRET_KEY": "e2e-test-secret-key-do-not-use-in-prod",
        "TOKEN_ENCRYPTION_KEY": "e2e-test-encryption-key-32-bytes",
        "ENV": "test",
        "LOG_LEVEL": "WARNING",
        "GOOGLE_ADS_CLIENT_ID": "e2e-test-client-id",
        "GOOGLE_ADS_CLIENT_SECRET": "e2e-test-client-secret",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "e2e-test-developer-token",
        "APP_URL": "http://localhost:8000",
    }
    for k, v in env_patch.items():
        original[k] = os.environ.get(k)
        os.environ[k] = v

    # Invalidate any cached Settings — subsequent get_settings() calls will
    # re-read the patched env vars.
    from adcopilot.config import get_settings

    get_settings.cache_clear()

    yield env_patch

    for k, prev in original.items():
        if prev is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = prev
    get_settings.cache_clear()


@pytest_asyncio.fixture(scope="session")
async def schema_setup(e2e_env: dict[str, str]) -> AsyncGenerator[None, None]:
    """Run the full Alembic migration chain against the test database.

    Using migrations (rather than ``Base.metadata.create_all``) guarantees the
    named ``uq_*`` UNIQUE constraints exist — these are required by the
    ``INSERT ... ON CONFLICT ON CONSTRAINT`` upserts used throughout the
    snapshot repository.
    """
    import pathlib

    from alembic import command
    from alembic.config import Config

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(repo_root / "adcopilot/infrastructure/db/alembic"))
    cfg.set_main_option("sqlalchemy.url", e2e_env["DATABASE_URL"])

    # Drop any pre-existing schema so each session starts clean.  When the test
    # DB is provisioned fresh (testcontainers) this is a no-op, but for the
    # CI/local path with a persistent DB it is essential for idempotency.
    engine = create_async_engine(e2e_env["DATABASE_URL"])
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()

    command.upgrade(cfg, "head")

    yield


@pytest_asyncio.fixture
async def db_engine(
    schema_setup: None, e2e_env: dict[str, str]
) -> AsyncGenerator[AsyncEngine, None]:
    """Provide an AsyncEngine connected to the migrated test database."""
    engine = create_async_engine(e2e_env["DATABASE_URL"])
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_db(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Truncate all app tables before each test — guarantees determinism.

    Runs before the test; no teardown needed because the next test will
    truncate again.
    """
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def e2e_settings(e2e_env: dict[str, str]) -> Any:
    """Return a fresh Settings instance bound to the test environment."""
    from adcopilot.config import Settings

    return Settings()  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _flush_redis(redis_url: str, clean_db: None) -> Generator[None, None, None]:
    """Flush the test Redis DB before each test to avoid cross-test state."""
    import redis

    client = redis.Redis.from_url(redis_url)
    try:
        client.flushdb()
    except Exception:
        # If Redis is down the test will fail for other reasons — don't mask.
        pass
    finally:
        client.close()
    yield
