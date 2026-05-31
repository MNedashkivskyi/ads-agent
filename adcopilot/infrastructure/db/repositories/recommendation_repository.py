"""SQLAlchemy implementation of RecommendationRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.db.models import RecommendationModel


def _model_to_domain(m: RecommendationModel) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(m.id)),
        account_id=AccountId(str(m.account_id)),
        kind=RecommendationKind(m.kind),
        severity=RecommendationSeverity(m.severity),
        status=RecommendationStatus(m.status),
        target=dict(m.target),
        payload=dict(m.payload),
        evidence=dict(m.evidence),
        target_hash=m.target_hash,
        estimated_monthly_savings_micros=m.estimated_monthly_savings_micros,
        explanation=m.explanation,
        created_at=m.created_at,
    )


class SqlRecommendationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, rec_id: RecommendationId) -> Recommendation | None:
        result = await self._session.execute(
            select(RecommendationModel).where(RecommendationModel.id == uuid.UUID(rec_id))
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None

    async def list_pending(self, account_id: AccountId) -> list[Recommendation]:
        result = await self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.account_id == uuid.UUID(account_id),
                RecommendationModel.status == RecommendationStatus.PENDING.value,
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def list_active_dedup_keys(
        self, account_id: AccountId
    ) -> set[tuple[RecommendationKind, str]]:
        """Return (kind, target_hash) for all recs that should block new duplicates.

        Includes PENDING, APPROVED, EXECUTED, DECLINED, FAILED — everything
        except EXPIRED. This prevents the engine from re-creating a rec that
        the user has already acted on or that is still being processed.
        """
        active_statuses = [
            RecommendationStatus.PENDING.value,
            RecommendationStatus.APPROVED.value,
            RecommendationStatus.EXECUTED.value,
            RecommendationStatus.DECLINED.value,
            RecommendationStatus.FAILED.value,
        ]
        result = await self._session.execute(
            select(RecommendationModel.kind, RecommendationModel.target_hash).where(
                RecommendationModel.account_id == uuid.UUID(account_id),
                RecommendationModel.status.in_(active_statuses),
            )
        )
        return {(RecommendationKind(row.kind), row.target_hash) for row in result.all()}

    async def save(self, rec: Recommendation) -> None:
        m = RecommendationModel()
        m.id = uuid.UUID(rec.id)
        m.account_id = uuid.UUID(rec.account_id)
        m.kind = rec.kind.value
        m.severity = rec.severity.value
        m.status = rec.status.value
        m.target = rec.target
        m.payload = rec.payload
        m.evidence = rec.evidence
        m.target_hash = rec.target_hash
        m.estimated_monthly_savings_micros = rec.estimated_monthly_savings_micros
        m.explanation = rec.explanation
        m.created_at = rec.created_at
        m.updated_at = datetime.now(tz=UTC)
        self._session.add(m)

    async def update_status(self, rec_id: RecommendationId, status: RecommendationStatus) -> None:
        result = await self._session.execute(
            select(RecommendationModel).where(RecommendationModel.id == uuid.UUID(rec_id))
        )
        m = result.scalar_one_or_none()
        if m:
            m.status = status.value

    async def expire_open_for_campaign(self, account_id: AccountId, campaign_id: int) -> int:
        """Mark every still-open rec targeting a (removed) campaign EXPIRED.

        "Open" means PENDING / FAILED / APPROVED — i.e. anything the user could
        still act on or retry. Used to self-heal the list when a campaign is
        found to no longer exist, without re-running full detection. Returns the
        number of recommendations expired.
        """
        from sqlalchemy import update

        stmt = (
            update(RecommendationModel)
            .where(
                RecommendationModel.account_id == uuid.UUID(account_id),
                RecommendationModel.target["campaign_id"].astext == str(campaign_id),
                RecommendationModel.status.in_(
                    [
                        RecommendationStatus.PENDING.value,
                        RecommendationStatus.FAILED.value,
                        RecommendationStatus.APPROVED.value,
                    ]
                ),
            )
            .values(
                status=RecommendationStatus.EXPIRED.value,
                updated_at=datetime.now(tz=UTC),
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount or 0

    async def expire_pending_not_matching(
        self, account_id: AccountId, keep_keys: set[tuple[str, str]]
    ) -> int:
        """Expire PENDING recs whose (kind, target_hash) is not in keep_keys.

        Called after a detection run so the list only shows currently-actual
        recommendations: any still-open suggestion that the latest run no longer
        produces (issue resolved) is moved to EXPIRED. Only PENDING recs are
        touched — APPROVED / EXECUTED / DECLINED / FAILED reflect user/worker
        actions and are left intact. Returns the number expired.
        """
        result = await self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.account_id == uuid.UUID(account_id),
                RecommendationModel.status == RecommendationStatus.PENDING.value,
            )
        )
        count = 0
        now = datetime.now(tz=UTC)
        for m in result.scalars().all():
            if (m.kind, m.target_hash) not in keep_keys:
                m.status = RecommendationStatus.EXPIRED.value
                m.updated_at = now
                count += 1
        return count

    async def update_explanation(self, rec_id: RecommendationId, explanation: str) -> None:
        result = await self._session.execute(
            select(RecommendationModel).where(RecommendationModel.id == uuid.UUID(rec_id))
        )
        m = result.scalar_one_or_none()
        if m:
            m.explanation = explanation

    async def list_executed_in_date_range(self, start: date, end: date) -> list[Recommendation]:
        from sqlalchemy import func as sqlfunc

        result = await self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.status == RecommendationStatus.EXECUTED.value,
                sqlfunc.date(RecommendationModel.updated_at) >= start,
                sqlfunc.date(RecommendationModel.updated_at) <= end,
            )
        )
        return [_model_to_domain(m) for m in result.scalars().all()]
