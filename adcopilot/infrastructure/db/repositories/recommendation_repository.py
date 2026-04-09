"""SQLAlchemy implementation of RecommendationRepository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
            select(RecommendationModel).where(
                RecommendationModel.id == uuid.UUID(rec_id)
            )
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

    async def update_status(
        self, rec_id: RecommendationId, status: RecommendationStatus
    ) -> None:
        result = await self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.id == uuid.UUID(rec_id)
            )
        )
        m = result.scalar_one_or_none()
        if m:
            m.status = status.value

    async def update_explanation(self, rec_id: RecommendationId, explanation: str) -> None:
        result = await self._session.execute(
            select(RecommendationModel).where(
                RecommendationModel.id == uuid.UUID(rec_id)
            )
        )
        m = result.scalar_one_or_none()
        if m:
            m.explanation = explanation
