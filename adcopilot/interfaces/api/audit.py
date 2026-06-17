"""Free-audit funnel API.

- Phase 0: session promotion (T0.3).
- Phase 1: report summary, evidence drill-down, methodology (T1.6, T1.8).
- Phase 2b: gated preview vs. full findings (T2.2), branded PDF (T2.3), and a
  signed shareable link (T2.4).

The public read-only OAuth connect lives in oauth.py (/oauth/audit/*).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from adcopilot.application.use_cases.promote_audit_session import PromoteAuditSessionUseCase
from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])

_MICROS = 1_000_000


class PromoteRequest(BaseModel):
    user_id: str
    account_id: str


def _report_summary(report: object) -> dict[str, object]:
    return {
        "id": report.id,  # type: ignore[attr-defined]
        "currency": report.currency,  # type: ignore[attr-defined]
        "window_start": report.window_start.isoformat(),  # type: ignore[attr-defined]
        "window_end": report.window_end.isoformat(),  # type: ignore[attr-defined]
        "total_spend_micros": report.total_spend_micros,  # type: ignore[attr-defined]
        "headline_waste_micros": report.headline_waste_micros,  # type: ignore[attr-defined]
        "annual_waste_micros": report.annual_waste_micros,  # type: ignore[attr-defined]
        "waste_pct": round(report.waste_pct, 4),  # type: ignore[attr-defined]
        "measurement_gap_pct": report.measurement_gap_pct,  # type: ignore[attr-defined]
        "confidence": report.confidence.value,  # type: ignore[attr-defined]
        "methodology_version": report.methodology_version,  # type: ignore[attr-defined]
    }


def _finding_dict(f: object) -> dict[str, object]:
    return {
        "category": f.category.value,  # type: ignore[attr-defined]
        "tier": f.tier.value,  # type: ignore[attr-defined]
        "title": f.title,  # type: ignore[attr-defined]
        "severity": f.severity,  # type: ignore[attr-defined]
        "amount_micros": f.amount_micros,  # type: ignore[attr-defined]
        "evidence": f.evidence,  # type: ignore[attr-defined]
    }


async def _load_report(settings: Settings, report_id: str) -> object | None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import SqlWasteReportRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            return await SqlWasteReportRepository(session).get(report_id)
    finally:
        await engine.dispose()


async def _load_report_and_findings(
    settings: Settings, report_id: str
) -> tuple[object | None, list]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlWasteFindingRepository,
        SqlWasteReportRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            report = await SqlWasteReportRepository(session).get(report_id)
            findings = (
                await SqlWasteFindingRepository(session).list_for_report(report_id)
                if report
                else []
            )
    finally:
        await engine.dispose()
    return report, findings


@router.post("/sessions/{session_id}/promote")
async def promote_audit_session(
    session_id: str,
    body: PromoteRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Claim an anonymous audit session for the signed-up user (T0.3)."""
    if current_user != body.user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import SqlAuditSessionRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            use_case = PromoteAuditSessionUseCase(SqlAuditSessionRepository(session))
            promoted = await use_case.execute(
                session_id=session_id, user_id=body.user_id, account_id=body.account_id
            )
    finally:
        await engine.dispose()

    if promoted:
        from adcopilot.observability import analytics

        analytics.audit_session_promoted(session_id, body.user_id)
    logger.info(
        "audit.session.promote", session_id=session_id, user_id=body.user_id, promoted=promoted
    )
    return {"session_id": session_id, "promoted": promoted}


@router.get("/sessions/{session_id}")
async def get_audit_session_status(
    session_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Poll a (possibly anonymous) audit session's status + report id (T2.1).

    The scan-ritual page polls this until status is READY (then loads the report)
    or FAILED.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlAuditSessionRepository,
        SqlWasteReportRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            audit = await SqlAuditSessionRepository(session).get(session_id)
            if audit is None:
                raise HTTPException(status_code=404, detail="Sesja audytu nie istnieje")
            report_id = await SqlWasteReportRepository(session).get_id_for_session(session_id)
    finally:
        await engine.dispose()
    return {"session_id": session_id, "status": audit.status.value, "report_id": report_id}


@router.delete("/sessions/{session_id}")
async def delete_audit_session(
    session_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """GDPR erasure on request — purge a session and its report/findings.

    Public: the session id is the visitor's own capability (from the scan URL).
    The read-only token already auto-expires (Redis TTL).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.audit_repository import SqlAuditSessionRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            deleted = await SqlAuditSessionRepository(session).delete(session_id)
    finally:
        await engine.dispose()
    logger.info("audit.session.erased", session_id=session_id, deleted=deleted)
    return {"session_id": session_id, "deleted": deleted}


@router.post("/sessions/{session_id}/bridge")
async def bridge_audit_session(
    session_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Claim the audit for the signed-up user's matching linked account, then kick off
    the first snapshot so real recommendations appear (onboarding bridge).
    """
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.bridge_audit_session import BridgeAuditSessionUseCase
    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlAuditSessionRepository,
        SqlWasteReportRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            use_case = BridgeAuditSessionUseCase(
                SqlAuditSessionRepository(session),
                SqlGoogleAdsAccountRepository(session),
                SqlWasteReportRepository(session),
            )
            account_id = await use_case.execute(session_id=session_id, user_id=current_user)
    finally:
        await engine.dispose()

    if account_id:
        from adcopilot.interfaces.worker.tasks import snapshot_account_task

        snapshot_account_task.delay(account_id, datetime.now(UTC).date().isoformat())
    logger.info("audit.session.bridge", session_id=session_id, account_id=account_id)
    return {"session_id": session_id, "bridged": account_id is not None, "account_id": account_id}


@router.get("/accounts/{account_id}/report")
async def get_account_audit_report(
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """The audit report tied to a linked account — for the one-time dashboard banner."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.audit_repository import SqlWasteReportRepository
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
            if account is None or str(account.user_id) != current_user:
                raise HTTPException(status_code=404, detail="Konto nie zostało znalezione")
            report = await SqlWasteReportRepository(session).get_for_account(account_id)
    finally:
        await engine.dispose()

    return {"account_id": account_id, "report": _report_summary(report) if report else None}


@router.get("/accounts/{account_id}/recovery")
async def get_account_recovery(
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """The recovery meter for a linked account: how much of the audit-identified
    waste has been recovered so far (Audit Funnel Phase 4 — retention loop).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.audit_repository import (
        SqlRecoveryLedgerRepository,
        SqlWasteReportRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
            if account is None or str(account.user_id) != current_user:
                raise HTTPException(status_code=404, detail="Konto nie zostało znalezione")
            ledger = SqlRecoveryLedgerRepository(session)
            recovered = await ledger.recovered_total_micros(account_id)
            entries = await ledger.list_for_account(account_id)
            report = await SqlWasteReportRepository(session).get_for_account(account_id)
    finally:
        await engine.dispose()

    return {
        "account_id": account_id,
        "recovered_micros": recovered,
        "applied_count": len(entries),
        "identified_annual_waste_micros": report.annual_waste_micros if report else 0,
        "currency": report.currency if report else "PLN",
    }


@router.get("/methodology")
async def audit_methodology() -> dict[str, object]:
    """Public "how we calculate this" content (T1.8)."""
    from adcopilot.application.audit.methodology import METHODOLOGY

    return METHODOLOGY


@router.get("/reports/{report_id}")
async def get_waste_report(
    report_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Public read of a waste-report summary — the audit reveal (T1.6)."""
    report = await _load_report(settings, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Raport nie został znaleziony")
    from adcopilot.observability import analytics

    analytics.audit_report_viewed(report_id)
    return _report_summary(report)


@router.get("/reports/{report_id}/findings")
async def get_waste_report_findings(
    report_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Public *free preview* — the top findings only. The full list is gated
    behind a share link or signup (T2.2 / T1.6).
    """
    from adcopilot.application.audit.report_view import preview_findings

    _, findings = await _load_report_and_findings(settings, report_id)
    shown, withheld = preview_findings(findings)
    return {
        "report_id": report_id,
        "gated": True,
        "withheld_count": withheld,
        "findings": [_finding_dict(f) for f in shown],
    }


@router.post("/reports/{report_id}/share")
async def create_share_link(
    report_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Mint a signed, expiring link that unlocks the full report (T2.4)."""
    from adcopilot.security.audit_share_token import DEFAULT_EXPIRY_DAYS, issue_share_token

    token = issue_share_token(report_id, settings.SECRET_KEY)
    base = settings.APP_URL.rstrip("/") if settings.APP_URL else ""
    logger.info("audit.report.share", report_id=report_id, user_id=current_user)
    return {
        "token": token,
        "share_url": f"{base}/audit/shared/{token}",
        "expires_in_days": DEFAULT_EXPIRY_DAYS,
    }


@router.get("/shared/{token}")
async def get_shared_report(
    token: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Public view of a shared report — full report + all findings (T2.4)."""
    from adcopilot.security.audit_share_token import ShareTokenInvalid, verify_share_token

    try:
        report_id = verify_share_token(token, settings.SECRET_KEY)
    except ShareTokenInvalid as exc:
        raise HTTPException(status_code=404, detail="Link wygasł lub jest nieprawidłowy") from exc

    report, findings = await _load_report_and_findings(settings, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Raport nie został znaleziony")
    return {
        "report": _report_summary(report),
        "gated": False,
        "findings": [_finding_dict(f) for f in findings],
    }


@router.get("/reports/{report_id}/pdf")
async def get_waste_report_pdf(
    report_id: str,
    token: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Branded PDF of the full report (T2.3), gated by the report's share token."""
    from adcopilot.infrastructure.reporting.pdf_renderer import render_waste_audit_pdf
    from adcopilot.security.audit_share_token import ShareTokenInvalid, verify_share_token

    try:
        if verify_share_token(token, settings.SECRET_KEY) != report_id:
            raise HTTPException(status_code=403, detail="Brak dostępu")
    except ShareTokenInvalid as exc:
        raise HTTPException(status_code=403, detail="Brak dostępu") from exc

    report, findings = await _load_report_and_findings(settings, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Raport nie został znaleziony")

    pdf = render_waste_audit_pdf(
        {
            "headline_waste_pln": report.headline_waste_micros / _MICROS,  # type: ignore[attr-defined]
            "annual_waste_pln": report.annual_waste_micros / _MICROS,  # type: ignore[attr-defined]
            "waste_pct": report.waste_pct,  # type: ignore[attr-defined]
            "measurement_gap_pct": report.measurement_gap_pct,  # type: ignore[attr-defined]
            "confidence": report.confidence.value,  # type: ignore[attr-defined]
            "period": (
                f"{report.window_start.isoformat()} — {report.window_end.isoformat()}"  # type: ignore[attr-defined]
            ),
            "findings": [
                {
                    "title": f.title,
                    "amount_pln": (
                        f.amount_micros / _MICROS if f.amount_micros is not None else None
                    ),
                    "tier": f.tier.value,
                }
                for f in findings
            ],
        }
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="audyt-{report_id}.pdf"'},
    )
