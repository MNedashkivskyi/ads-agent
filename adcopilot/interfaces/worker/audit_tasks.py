"""Celery task: run a free-audit scan (Audit Funnel Phase 2 / T2.1).

Reads the read-only refresh token stashed at the OAuth callback, pulls Google
Ads read-only, runs the waste engine, and persists the report — walking the
session to READY (or FAILED). Thin wrapper around RunAuditScanUseCase; the live
Google Ads reader is verified in staging.
"""

from __future__ import annotations

import asyncio

import structlog

from adcopilot.interfaces.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.audit_tasks.run_audit_scan_task",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def run_audit_scan_task(audit_session_id: str) -> dict[str, object]:
    return asyncio.run(_run_audit_scan(audit_session_id))


def _decrypt_token(enc: bytes, token_key: str) -> str:
    import base64
    import hashlib
    import json

    from cryptography.fernet import Fernet

    fernet_key = base64.urlsafe_b64encode(hashlib.sha256(token_key.encode()).digest())
    payload = json.loads(Fernet(fernet_key).decrypt(enc).decode())
    return str(payload["refresh_token"])


async def _mark_failed(settings: object, audit_session_id: str) -> None:
    """Mark the session FAILED in its own transaction (survives a scan error)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.audit import AuditStatus
    from adcopilot.infrastructure.db.repositories.audit_repository import SqlAuditSessionRepository

    engine = create_async_engine(settings.DATABASE_URL)  # type: ignore[attr-defined]
    try:
        async with AsyncSession(engine) as session, session.begin():
            await SqlAuditSessionRepository(session).set_status(
                audit_session_id, AuditStatus.FAILED
            )
    finally:
        await engine.dispose()


async def _run_audit_scan(audit_session_id: str) -> dict[str, object]:
    from datetime import UTC, datetime

    import redis as redis_sync
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.compute_waste_report import (
        ComputeAndStoreWasteReportUseCase,
    )
    from adcopilot.application.use_cases.run_audit_scan import RunAuditScanUseCase
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.audit.google_ads_scan_reader import GoogleAdsAuditScanReader
    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlAuditSessionRepository,
        SqlWasteFindingRepository,
        SqlWasteReportRepository,
    )

    settings = get_settings()
    redis_client = redis_sync.Redis.from_url(
        settings.REDIS_URL, socket_connect_timeout=5, socket_timeout=5
    )
    token_redis_key = f"audit_token:{audit_session_id}"
    enc = redis_client.get(token_redis_key)
    if not enc:
        logger.warning("audit_scan.token_missing", audit_session_id=audit_session_id)
        await _mark_failed(settings, audit_session_id)
        return {"status": "failed", "reason": "token_missing"}

    refresh_token = _decrypt_token(enc, settings.TOKEN_ENCRYPTION_KEY)
    reader = GoogleAdsAuditScanReader(settings)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            compute = ComputeAndStoreWasteReportUseCase(
                SqlWasteReportRepository(session), SqlWasteFindingRepository(session)
            )
            use_case = RunAuditScanUseCase(reader, SqlAuditSessionRepository(session), compute)
            report_id = await use_case.execute(
                audit_session_id=audit_session_id,
                refresh_token=refresh_token,
                today=datetime.now(UTC).date(),
                days=30,
            )
    except Exception:
        await _mark_failed(settings, audit_session_id)
        raise
    finally:
        await engine.dispose()

    # Token is single-use — drop it once the scan is done (GDPR minimisation).
    try:
        redis_client.delete(token_redis_key)
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.warning("audit_scan.token_cleanup_failed", audit_session_id=audit_session_id)

    logger.info("audit_scan.complete", audit_session_id=audit_session_id, report_id=report_id)
    return {"status": "ok", "report_id": report_id}
