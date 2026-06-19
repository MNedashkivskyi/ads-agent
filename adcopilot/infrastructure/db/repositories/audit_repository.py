"""Repositories for the audit funnel (Audit Funnel Phase 0 / Tasks 0.1, 0.3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.audit import (
    AuditSession,
    AuditSource,
    AuditStatus,
    FindingTier,
    RecoveryLedgerEntry,
    ReportConfidence,
    WasteCategory,
    WasteFinding,
    WasteReport,
)
from adcopilot.infrastructure.db.models import (
    AuditSessionModel,
    RecoveryLedgerModel,
    WasteFindingModel,
    WasteReportModel,
)


def _opt_str(v: uuid.UUID | None) -> str | None:
    return str(v) if v is not None else None


def _opt_uuid(v: str | None) -> uuid.UUID | None:
    return uuid.UUID(v) if v else None


def session_to_domain(m: AuditSessionModel) -> AuditSession:
    return AuditSession(
        id=str(m.id),
        google_customer_id=m.google_customer_id,
        status=AuditStatus(m.status),
        oauth_scope=m.oauth_scope,
        source=AuditSource(m.source),
        email=m.email,
        user_id=_opt_str(m.user_id),
        account_id=_opt_str(m.account_id),
        agency_org_id=_opt_str(m.agency_org_id),
        consent_at=m.consent_at,
        created_at=m.created_at,
        expires_at=m.expires_at,
    )


def report_to_domain(m: WasteReportModel) -> WasteReport:
    return WasteReport(
        id=str(m.id),
        window_start=m.window_start,
        window_end=m.window_end,
        total_spend_micros=m.total_spend_micros,
        headline_waste_micros=m.headline_waste_micros,
        measurement_gap_pct=m.measurement_gap_pct,
        confidence=ReportConfidence(m.confidence),
        currency=m.currency,
        methodology_version=m.methodology_version,
        audit_session_id=_opt_str(m.audit_session_id),
        account_id=_opt_str(m.account_id),
        computed_at=m.computed_at,
    )


def finding_to_domain(m: WasteFindingModel) -> WasteFinding:
    return WasteFinding(
        id=str(m.id),
        report_id=str(m.report_id),
        category=WasteCategory(m.category),
        tier=FindingTier(m.tier),
        title=m.title,
        severity=m.severity,
        amount_micros=m.amount_micros,
        evidence=dict(m.evidence or {}),
        recommendation_id=_opt_str(m.recommendation_id),
    )


def recovery_to_domain(m: RecoveryLedgerModel) -> RecoveryLedgerEntry:
    return RecoveryLedgerEntry(
        id=str(m.id),
        account_id=str(m.account_id),
        applied_at=m.applied_at,
        method=m.method,
        finding_id=_opt_str(m.finding_id),
        recommendation_id=_opt_str(m.recommendation_id),
        baseline_metric=dict(m.baseline_metric or {}),
        realized_saving_micros=m.realized_saving_micros,
        measured_at=m.measured_at,
    )


class SqlAuditSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        google_customer_id: str | None = None,
        source: AuditSource = AuditSource.LANDING,
        consent_at: datetime | None = None,
        expires_at: datetime | None = None,
        agency_org_id: str | None = None,
    ) -> AuditSession:
        m = AuditSessionModel(
            id=uuid.uuid4(),
            google_customer_id=google_customer_id,
            status=AuditStatus.PENDING.value,
            source=source.value,
            consent_at=consent_at,
            expires_at=expires_at,
            agency_org_id=_opt_uuid(agency_org_id),
        )
        self._session.add(m)
        await self._session.flush()
        return session_to_domain(m)

    async def get(self, session_id: str) -> AuditSession | None:
        m = await self._session.get(AuditSessionModel, uuid.UUID(session_id))
        return session_to_domain(m) if m else None

    async def set_status(self, session_id: str, status: AuditStatus) -> None:
        await self._session.execute(
            update(AuditSessionModel)
            .where(AuditSessionModel.id == uuid.UUID(session_id))
            .values(status=status.value)
        )

    async def set_email(self, session_id: str, email: str) -> None:
        await self._session.execute(
            update(AuditSessionModel)
            .where(AuditSessionModel.id == uuid.UUID(session_id))
            .values(email=email)
        )

    async def set_customer_id(self, session_id: str, google_customer_id: str) -> None:
        """Set the resolved Google customer id (called by the scan worker, Phase 2)."""
        await self._session.execute(
            update(AuditSessionModel)
            .where(AuditSessionModel.id == uuid.UUID(session_id))
            .values(google_customer_id=google_customer_id)
        )

    async def promote(self, session_id: str, *, user_id: str, account_id: str) -> bool:
        """Attach a real user/account to an anonymous session exactly once (T0.3)."""
        result = await self._session.execute(
            update(AuditSessionModel)
            .where(
                AuditSessionModel.id == uuid.UUID(session_id),
                AuditSessionModel.user_id.is_(None),
            )
            .values(
                status=AuditStatus.PROMOTED.value,
                user_id=uuid.UUID(user_id),
                account_id=uuid.UUID(account_id),
            )
        )
        return result.rowcount > 0

    async def delete(self, session_id: str) -> bool:
        """GDPR erasure on request: delete one session + its cascaded reports/findings."""
        result = await self._session.execute(
            delete(AuditSessionModel).where(AuditSessionModel.id == uuid.UUID(session_id))
        )
        return result.rowcount > 0

    async def delete_stale(self, *, before: datetime) -> int:
        """GDPR: delete anonymous (un-promoted) sessions created before ``before``.

        Their waste reports and findings cascade via FK. Returns the number of
        sessions deleted.
        """
        result = await self._session.execute(
            delete(AuditSessionModel).where(
                AuditSessionModel.user_id.is_(None),
                AuditSessionModel.created_at < before,
            )
        )
        return result.rowcount


class SqlWasteReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        window_start: date,
        window_end: date,
        total_spend_micros: int,
        headline_waste_micros: int,
        measurement_gap_pct: float,
        confidence: ReportConfidence,
        audit_session_id: str | None = None,
        account_id: str | None = None,
        methodology_version: str = "1",
    ) -> WasteReport:
        m = WasteReportModel(
            id=uuid.uuid4(),
            audit_session_id=_opt_uuid(audit_session_id),
            account_id=_opt_uuid(account_id),
            window_start=window_start,
            window_end=window_end,
            total_spend_micros=total_spend_micros,
            headline_waste_micros=headline_waste_micros,
            measurement_gap_pct=measurement_gap_pct,
            confidence=confidence.value,
            methodology_version=methodology_version,
        )
        self._session.add(m)
        await self._session.flush()
        return report_to_domain(m)

    async def get(self, report_id: str) -> WasteReport | None:
        m = await self._session.get(WasteReportModel, uuid.UUID(report_id))
        return report_to_domain(m) if m else None

    async def get_id_for_session(self, audit_session_id: str) -> str | None:
        """The latest report id for an audit session (for scan-status polling)."""
        row = (
            await self._session.execute(
                select(WasteReportModel.id)
                .where(WasteReportModel.audit_session_id == uuid.UUID(audit_session_id))
                .order_by(WasteReportModel.computed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return str(row) if row else None

    async def get_for_account(self, account_id: str) -> WasteReport | None:
        """The latest waste report tied to a linked account (the onboarding bridge)."""
        m = (
            await self._session.execute(
                select(WasteReportModel)
                .where(WasteReportModel.account_id == uuid.UUID(account_id))
                .order_by(WasteReportModel.computed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return report_to_domain(m) if m else None

    async def set_account_for_session(self, audit_session_id: str, account_id: str) -> None:
        """Tie an audit's report(s) to a linked account (after the session is promoted)."""
        await self._session.execute(
            update(WasteReportModel)
            .where(WasteReportModel.audit_session_id == uuid.UUID(audit_session_id))
            .values(account_id=uuid.UUID(account_id))
        )


class SqlWasteFindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        report_id: str,
        category: WasteCategory,
        tier: FindingTier,
        title: str,
        severity: str = "MEDIUM",
        amount_micros: int | None = None,
        evidence: dict[str, object] | None = None,
        recommendation_id: str | None = None,
    ) -> WasteFinding:
        m = WasteFindingModel(
            id=uuid.uuid4(),
            report_id=uuid.UUID(report_id),
            category=category.value,
            tier=tier.value,
            title=title,
            severity=severity,
            amount_micros=amount_micros,
            evidence=evidence or {},
            recommendation_id=_opt_uuid(recommendation_id),
        )
        self._session.add(m)
        await self._session.flush()
        return finding_to_domain(m)

    async def list_for_report(self, report_id: str) -> list[WasteFinding]:
        rows = (
            await self._session.execute(
                select(WasteFindingModel)
                .where(WasteFindingModel.report_id == uuid.UUID(report_id))
                .order_by(WasteFindingModel.amount_micros.desc().nullslast())
            )
        ).scalars()
        return [finding_to_domain(m) for m in rows]


class SqlRecoveryLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        account_id: str,
        method: str = "projected",
        finding_id: str | None = None,
        recommendation_id: str | None = None,
        baseline_metric: dict[str, object] | None = None,
        realized_saving_micros: int | None = None,
        measured_at: datetime | None = None,
    ) -> RecoveryLedgerEntry:
        m = RecoveryLedgerModel(
            id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            method=method,
            finding_id=_opt_uuid(finding_id),
            recommendation_id=_opt_uuid(recommendation_id),
            baseline_metric=baseline_metric or {},
            realized_saving_micros=realized_saving_micros,
            measured_at=measured_at,
        )
        self._session.add(m)
        await self._session.flush()
        return recovery_to_domain(m)

    async def list_for_account(self, account_id: str) -> list[RecoveryLedgerEntry]:
        rows = (
            await self._session.execute(
                select(RecoveryLedgerModel)
                .where(RecoveryLedgerModel.account_id == uuid.UUID(account_id))
                .order_by(RecoveryLedgerModel.applied_at.desc())
            )
        ).scalars()
        return [recovery_to_domain(m) for m in rows]

    async def recovered_total_micros(self, account_id: str) -> int:
        """Sum of realised savings for an account — powers the recovery meter."""
        total = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(RecoveryLedgerModel.realized_saving_micros), 0)
                ).where(RecoveryLedgerModel.account_id == uuid.UUID(account_id))
            )
        ).scalar_one()
        return int(total or 0)

    async def get(self, entry_id: str) -> RecoveryLedgerEntry | None:
        m = await self._session.get(RecoveryLedgerModel, uuid.UUID(entry_id))
        return recovery_to_domain(m) if m else None

    async def list_due_for_settlement(
        self, *, before: datetime, limit: int = 200
    ) -> list[RecoveryLedgerEntry]:
        """Projected entries applied before ``before`` and not yet measured (settle task)."""
        rows = (
            await self._session.execute(
                select(RecoveryLedgerModel)
                .where(
                    RecoveryLedgerModel.method == "projected",
                    RecoveryLedgerModel.measured_at.is_(None),
                    RecoveryLedgerModel.applied_at < before,
                )
                .order_by(RecoveryLedgerModel.applied_at)
                .limit(limit)
            )
        ).scalars()
        return [recovery_to_domain(m) for m in rows]

    async def settle(
        self, entry_id: str, *, realized_saving_micros: int, measured_at: datetime
    ) -> None:
        """Reconcile a projected entry to its measured saving."""
        await self._session.execute(
            update(RecoveryLedgerModel)
            .where(RecoveryLedgerModel.id == uuid.UUID(entry_id))
            .values(
                method="measured",
                realized_saving_micros=realized_saving_micros,
                measured_at=measured_at,
            )
        )
