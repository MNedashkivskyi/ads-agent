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
from adcopilot.observability import analytics

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
        analytics.audit_scan_failed(audit_session_id, "token_missing")
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
        analytics.audit_scan_failed(audit_session_id, "scan_error")
        raise
    finally:
        await engine.dispose()

    # Token is single-use — drop it once the scan is done (GDPR minimisation).
    try:
        redis_client.delete(token_redis_key)
    except Exception:  # noqa: BLE001 — best-effort cleanup
        logger.warning("audit_scan.token_cleanup_failed", audit_session_id=audit_session_id)

    analytics.audit_scan_completed(audit_session_id, report_id)
    logger.info("audit_scan.complete", audit_session_id=audit_session_id, report_id=report_id)
    return {"status": "ok", "report_id": report_id}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.audit_tasks.purge_stale_audit_sessions_task"
)
def purge_stale_audit_sessions_task() -> dict[str, object]:
    """GDPR retention: delete anonymous audit data older than AUDIT_RETENTION_DAYS."""
    return asyncio.run(_purge_stale_audit_sessions())


async def _purge_stale_audit_sessions() -> dict[str, object]:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.audit_repository import SqlAuditSessionRepository

    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(days=settings.AUDIT_RETENTION_DAYS)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            purged = await SqlAuditSessionRepository(session).delete_stale(before=cutoff)
    finally:
        await engine.dispose()
    logger.info("audit_retention.purged", count=purged)
    return {"purged": purged}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.audit_tasks.settle_recovery_ledger_task"
)
def settle_recovery_ledger_task() -> dict[str, object]:
    """Reconcile projected savings to measured ones once the settle window passes
    (Audit Funnel Phase 4 — recovery meter). The reconciliation arithmetic is pure
    and unit-tested; the live per-campaign spend read is verified in staging.
    """
    return asyncio.run(_settle_recovery_ledger())


async def _settle_recovery_ledger() -> dict[str, object]:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.audit.recovery import reconcile_realized_saving
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlRecoveryLedgerRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

    settle_days = 28
    settings = get_settings()
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=settle_days)
    engine = create_async_engine(settings.DATABASE_URL)
    settled = 0
    try:
        async with AsyncSession(engine) as session, session.begin():
            ledger = SqlRecoveryLedgerRepository(session)
            snaps = SqlSnapshotRepository(session)
            due = await ledger.list_due_for_settlement(before=cutoff)
            for entry in due:
                bm = entry.baseline_metric or {}
                projected = int(bm.get("projected_micros") or entry.realized_saving_micros or 0)
                campaign_id = bm.get("campaign_id")
                realized = projected
                if campaign_id:
                    applied = entry.applied_at.date()
                    cid = int(campaign_id)
                    pre = await snaps.get_campaigns_date_range(
                        entry.account_id,
                        applied - timedelta(days=settle_days),
                        applied - timedelta(days=1),
                    )
                    post = await snaps.get_campaigns_date_range(
                        entry.account_id,
                        applied + timedelta(days=1),
                        applied + timedelta(days=settle_days),
                    )
                    base_cost = sum(s.cost_micros for s in pre if s.campaign_id == cid)
                    post_cost = sum(s.cost_micros for s in post if s.campaign_id == cid)
                    realized = reconcile_realized_saving(
                        projected_micros=projected,
                        baseline_cost_micros=base_cost,
                        post_cost_micros=post_cost,
                    )
                await ledger.settle(entry.id, realized_saving_micros=realized, measured_at=now)
                settled += 1
    finally:
        await engine.dispose()
    logger.info("recovery_ledger.settled", count=settled)
    return {"settled": settled}
