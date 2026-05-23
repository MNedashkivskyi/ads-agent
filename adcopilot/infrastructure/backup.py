"""Cloudflare R2 backup helpers for Postgres disaster recovery.

Public API
----------
run_backup()          -- pg_dump → gzip → upload to R2, return object key
download_backup(key)  -- download an object from R2 to a local path
list_backups()        -- list all backup objects sorted newest-first
delete_old_backups()  -- prune objects older than retain_days (default 30)

R2 credentials are read from Settings (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME).  All uploads use AES-256
server-side encryption.
"""

from __future__ import annotations

import gzip
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _r2_client():  # type: ignore[return]
    """Return a boto3 S3 client pre-configured for Cloudflare R2."""
    import boto3
    from botocore.config import Config

    from adcopilot.config import get_settings

    settings = get_settings()
    if not settings.R2_ACCOUNT_ID:
        raise RuntimeError("R2_ACCOUNT_ID is not configured")
    if not settings.R2_ACCESS_KEY_ID or not settings.R2_SECRET_ACCESS_KEY:
        raise RuntimeError("R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY are not configured")

    endpoint = f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _parse_db_url(database_url: str) -> dict[str, str | int]:
    """Return a dict with host/port/user/password/dbname from DATABASE_URL."""
    # Strip the asyncpg driver prefix so urlparse handles it correctly.
    normalized = database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(normalized)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_backup() -> str:
    """Run pg_dump, gzip the output, and upload to R2.

    Returns the R2 object key (e.g. ``backups/20240101-020000.sql.gz``).
    Raises on any subprocess or upload error.
    """
    from adcopilot.config import get_settings

    settings = get_settings()
    db = _parse_db_url(settings.DATABASE_URL)

    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    key = f"backups/{ts}.sql.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = str(db["password"])

    pg_dump_cmd = [
        "pg_dump",
        "-h",
        str(db["host"]),
        "-p",
        str(db["port"]),
        "-U",
        str(db["user"]),
        "--no-password",
        "--format=plain",
        str(db["dbname"]),
    ]

    # Write to a temp file so we can stream to R2 without buffering the whole
    # dump in memory.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sql.gz")
    os.close(tmp_fd)

    try:
        logger.info("backup.pg_dump.start", key=key, host=db["host"], dbname=db["dbname"])

        result = subprocess.run(  # noqa: UP022
            pg_dump_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=True,
        )

        with gzip.open(tmp_path, "wb") as gz:
            gz.write(result.stdout)

        compressed_size = Path(tmp_path).stat().st_size
        logger.info("backup.pg_dump.done", key=key, compressed_bytes=compressed_size)

        client = _r2_client()
        client.upload_file(
            tmp_path,
            settings.R2_BUCKET_NAME,
            key,
            ExtraArgs={"ServerSideEncryption": "AES256"},
        )

        logger.info("backup.upload.done", key=key, bucket=settings.R2_BUCKET_NAME)
        return key

    except subprocess.CalledProcessError as exc:
        logger.error(
            "backup.pg_dump.failed",
            returncode=exc.returncode,
            stderr=exc.stderr.decode(errors="replace"),
        )
        raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def download_backup(key: str, local_path: str) -> None:
    """Download *key* from R2 and write it to *local_path*."""
    from adcopilot.config import get_settings

    settings = get_settings()
    client = _r2_client()

    logger.info("backup.download.start", key=key, local_path=local_path)
    client.download_file(settings.R2_BUCKET_NAME, key, local_path)
    size = Path(local_path).stat().st_size
    logger.info("backup.download.done", key=key, bytes=size)


def list_backups() -> list[dict[str, object]]:
    """Return all backup objects in R2 sorted newest-first.

    Each entry is a dict with keys: ``key``, ``size`` (bytes),
    ``last_modified`` (timezone-aware datetime).
    """
    from adcopilot.config import get_settings

    settings = get_settings()
    client = _r2_client()

    paginator = client.get_paginator("list_objects_v2")
    backups: list[dict[str, object]] = []

    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix="backups/"):
        for obj in page.get("Contents", []):
            backups.append(
                {
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                }
            )

    return sorted(backups, key=lambda x: x["last_modified"], reverse=True)  # type: ignore[arg-type]


def delete_old_backups(retain_days: int = 30) -> int:
    """Delete backup objects older than *retain_days*.

    Returns the number of objects deleted.
    """
    from adcopilot.config import get_settings

    settings = get_settings()
    client = _r2_client()
    cutoff = datetime.now(UTC) - timedelta(days=retain_days)

    paginator = client.get_paginator("list_objects_v2")
    deleted = 0

    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME, Prefix="backups/"):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                client.delete_object(Bucket=settings.R2_BUCKET_NAME, Key=obj["Key"])
                deleted += 1
                logger.info("backup.pruned", key=obj["Key"])

    logger.info("backup.prune.done", deleted=deleted, retain_days=retain_days)
    return deleted
