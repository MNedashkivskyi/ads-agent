"""Repository for campaign_experiments (causal measurement)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_experiment import (
    CampaignExperiment,
    ExperimentChangeKind,
    ExperimentStatus,
    ExperimentVerdict,
)
from adcopilot.infrastructure.db.models import CampaignExperimentModel


def _to_domain(m: CampaignExperimentModel) -> CampaignExperiment:
    return CampaignExperiment(
        id=m.id,
        account_id=str(m.account_id),
        base_campaign_id=m.base_campaign_id,
        change_kind=ExperimentChangeKind(m.change_kind),
        change_payload=dict(m.change_payload or {}),
        traffic_split=m.traffic_split,
        status=ExperimentStatus(m.status),
        draft_resource_name=m.draft_resource_name,
        experiment_resource_name=m.experiment_resource_name,
        started_at=m.started_at,
        ends_at=m.ends_at,
        control_metrics=dict(m.control_metrics or {}),
        treatment_metrics=dict(m.treatment_metrics or {}),
        verdict=ExperimentVerdict(m.verdict),
        confidence=m.confidence,
        evaluated_at=m.evaluated_at,
        last_error=m.last_error,
        source_recommendation_id=m.source_recommendation_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_values(e: CampaignExperiment) -> dict:
    return {
        "id": e.id,
        "account_id": uuid.UUID(e.account_id),
        "base_campaign_id": e.base_campaign_id,
        "change_kind": e.change_kind.value,
        "change_payload": e.change_payload,
        "traffic_split": e.traffic_split,
        "status": e.status.value,
        "draft_resource_name": e.draft_resource_name,
        "experiment_resource_name": e.experiment_resource_name,
        "started_at": e.started_at,
        "ends_at": e.ends_at,
        "control_metrics": e.control_metrics,
        "treatment_metrics": e.treatment_metrics,
        "verdict": e.verdict.value,
        "confidence": e.confidence,
        "evaluated_at": e.evaluated_at,
        "last_error": e.last_error,
        "source_recommendation_id": e.source_recommendation_id,
        "updated_at": e.updated_at,
    }


class CampaignExperimentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, exp: CampaignExperiment) -> None:
        values = _to_values(exp)
        stmt = insert(CampaignExperimentModel).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in values if k not in ("id", "account_id")}
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
        await self._session.execute(stmt)

    async def get(self, experiment_id: uuid.UUID) -> CampaignExperiment | None:
        row = (
            await self._session.execute(
                select(CampaignExperimentModel).where(CampaignExperimentModel.id == experiment_id)
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list_for_account(self, account_id: str, *, limit: int = 100) -> list[CampaignExperiment]:
        rows = (
            await self._session.execute(
                select(CampaignExperimentModel)
                .where(CampaignExperimentModel.account_id == uuid.UUID(account_id))
                .order_by(CampaignExperimentModel.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_running(self, *, limit: int = 500) -> list[CampaignExperiment]:
        rows = (
            await self._session.execute(
                select(CampaignExperimentModel)
                .where(CampaignExperimentModel.status == ExperimentStatus.RUNNING.value)
                .limit(limit)
            )
        ).scalars().all()
        return [_to_domain(r) for r in rows]
