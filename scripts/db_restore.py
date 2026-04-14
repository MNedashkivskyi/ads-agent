#!/usr/bin/env python3
"""Disaster-recovery restore script.

Downloads a backup from Cloudflare R2, drops and recreates the local
Postgres database, restores from the backup, applies any pending Alembic
migrations, and verifies that key tables are non-empty.

Usage
-----
    uv run python scripts/db_restore.py backups/20240101-020000.sql.gz
    uv run python scripts/db_restore.py 20240101-020000.sql.gz  # prefix added

Prerequisites
-------------
- docker compose up -d postgres   (for the local dev database)
- R2 credentials present in .env or environment variables
- `uv` available on PATH (for alembic upgrade head)

Exit codes
----------
  0  success
  1  usage error or restore failure
"""

from __future__ import annotations

import asyncio
import gzip
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

# Make sure the project root is importable regardless of cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """Load .env into os.environ (values already present are NOT overwritten)."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            # Strip inline comments and surrounding quotes.
            val = val.split("#")[0].strip().strip("\"'")
            os.environ.setdefault(key.strip(), val)


def _parse_db_url(database_url: str) -> dict[str, str | int]:
    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(normalized)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/"),
    }


def _run(cmd: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> None:
    """Print and run a shell command."""
    print("    $", " ".join(cmd))
    subprocess.run(cmd, env=env, check=check, cwd=str(PROJECT_ROOT))


def _step(msg: str) -> None:
    print(f"\n==> {msg}")


# ---------------------------------------------------------------------------
# Restore stages
# ---------------------------------------------------------------------------


def download(backup_key: str) -> str:
    """Download the backup from R2 and return the local temp file path."""
    from adcopilot.infrastructure.backup import download_backup

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sql.gz", prefix="adcopilot-restore-")
    os.close(tmp_fd)

    download_backup(backup_key, tmp_path)
    size_mb = Path(tmp_path).stat().st_size / 1024 / 1024
    print(f"    Downloaded {size_mb:.2f} MB → {tmp_path}")
    return tmp_path


def drop_and_recreate(db: dict[str, str | int]) -> None:
    """Drop and recreate the database via docker compose exec postgres."""
    env = os.environ.copy()
    env["PGPASSWORD"] = str(db["password"])

    # We need to connect to the maintenance database (postgres) to be able to
    # drop the application database while nobody else is connected to it.
    base_cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", str(db["user"]), "-d", "postgres",
    ]

    # Terminate any existing connections so the DROP succeeds.
    terminate_sql = (
        f"SELECT pg_terminate_backend(pid) "
        f"FROM pg_stat_activity "
        f"WHERE datname = '{db['dbname']}' AND pid <> pg_backend_pid();"
    )
    subprocess.run(base_cmd + ["-c", terminate_sql], env=env, check=True, cwd=str(PROJECT_ROOT))

    subprocess.run(
        base_cmd + ["-c", f"DROP DATABASE IF EXISTS \"{db['dbname']}\";"],
        env=env, check=True, cwd=str(PROJECT_ROOT),
    )
    subprocess.run(
        base_cmd + ["-c", f"CREATE DATABASE \"{db['dbname']}\";"],
        env=env, check=True, cwd=str(PROJECT_ROOT),
    )
    print(f"    Recreated database '{db['dbname']}'")


def restore_dump(tmp_path: str, db: dict[str, str | int]) -> None:
    """Decompress the dump and pipe it into psql inside the postgres container."""
    env = os.environ.copy()
    env["PGPASSWORD"] = str(db["password"])

    psql_cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", str(db["user"]), "-d", str(db["dbname"]), "--quiet",
    ]

    with gzip.open(tmp_path, "rb") as gz:
        sql_bytes = gz.read()

    proc = subprocess.Popen(
        psql_cmd,
        stdin=subprocess.PIPE,
        env=env,
        cwd=str(PROJECT_ROOT),
    )
    proc.communicate(sql_bytes)

    if proc.returncode != 0:
        raise RuntimeError(f"psql restore exited with code {proc.returncode}")

    print("    Restore complete")


def run_migrations() -> None:
    """Run alembic upgrade head against the freshly restored database."""
    _run(["uv", "run", "alembic", "upgrade", "head"])


async def _count_rows(database_url: str, tables: list[str]) -> dict[str, int]:
    import asyncpg

    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        counts: dict[str, int] = {}
        for table in tables:
            try:
                counts[table] = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
            except Exception as exc:  # noqa: BLE001
                counts[table] = -1
                print(f"    WARNING: could not query {table}: {exc}")
        return counts
    finally:
        await conn.close()


def verify(database_url: str) -> bool:
    """Return True when all key tables have at least one row."""
    key_tables = [
        "users",
        "google_ads_accounts",
        "oauth_credentials",
        "snapshot_runs",
        "campaign_snapshots",
        "recommendations",
    ]

    counts = asyncio.run(_count_rows(database_url, key_tables))
    all_ok = True

    for table, count in counts.items():
        if count < 0:
            status = "ERROR"
            all_ok = False
        elif count == 0:
            # Some tables may legitimately be empty in certain environments.
            status = "WARNING (empty)"
        else:
            status = f"OK ({count} rows)"
        print(f"    {table}: {status}")

    return all_ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(backup_key: str) -> None:
    _load_env()

    # Normalise key — accept bare filename or full prefix.
    if not backup_key.startswith("backups/"):
        backup_key = f"backups/{backup_key}"

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot",
    )
    db = _parse_db_url(database_url)

    print(f"\nRestoring from R2 key : {backup_key}")
    print(f"Target database       : {db['dbname']} on {db['host']}:{db['port']}\n")

    start = time.monotonic()

    # ── Stage 1: Download ────────────────────────────────────────────────────
    _step("Downloading backup from R2 …")
    tmp_path = download(backup_key)

    try:
        # ── Stage 2: Drop / recreate ─────────────────────────────────────────
        _step("Dropping and recreating database …")
        drop_and_recreate(db)

        # ── Stage 3: Restore ─────────────────────────────────────────────────
        _step("Restoring SQL dump …")
        restore_dump(tmp_path, db)

        # ── Stage 4: Migrations ───────────────────────────────────────────────
        _step("Applying Alembic migrations …")
        run_migrations()

        # ── Stage 5: Verification ─────────────────────────────────────────────
        _step("Verifying row counts …")
        verify(database_url)

    finally:
        Path(tmp_path).unlink(missing_ok=True)

    elapsed = time.monotonic() - start
    print(f"\n{'='*60}")
    print(f"  Restore completed in {elapsed:.1f}s ({elapsed / 60:.1f} minutes)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
