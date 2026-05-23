"""Repository for ad_experiments table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import AdExperimentModel


class AdExperimentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        experiment_id: str,
        account_id: str,
        campaign_resource_name: str,
        ad_group_resource_name: str,
        control_ad_resource_name: str,
        variant_ad_resource_name: str,
        min_impressions: int,
        confidence_threshold: float,
        started_at: datetime,
    ) -> AdExperimentModel:
        model = AdExperimentModel(
            id=uuid.UUID(experiment_id),
            account_id=uuid.UUID(account_id),
            campaign_resource_name=campaign_resource_name,
            ad_group_resource_name=ad_group_resource_name,
            control_ad_resource_name=control_ad_resource_name,
            variant_ad_resource_name=variant_ad_resource_name,
            status="running",
            min_impressions=min_impressions,
            confidence_threshold=confidence_threshold,
            started_at=started_at,
            created_at=started_at,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def list_running(self, account_id: str) -> list[AdExperimentModel]:
        result = await self._session.execute(
            select(AdExperimentModel).where(
                AdExperimentModel.account_id == uuid.UUID(account_id),
                AdExperimentModel.status == "running",
            )
        )
        return list(result.scalars().all())

    async def list_for_account(self, account_id: str) -> list[AdExperimentModel]:
        result = await self._session.execute(
            select(AdExperimentModel)
            .where(
                AdExperimentModel.account_id == uuid.UUID(account_id),
            )
            .order_by(AdExperimentModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, experiment_id: str) -> AdExperimentModel | None:
        result = await self._session.execute(
            select(AdExperimentModel).where(
                AdExperimentModel.id == uuid.UUID(experiment_id),
            )
        )
        return result.scalar_one_or_none()

    async def update_metrics(
        self,
        experiment_id: str,
        control_metrics: dict,
        variant_metrics: dict,
    ) -> None:
        await self._session.execute(
            update(AdExperimentModel)
            .where(AdExperimentModel.id == uuid.UUID(experiment_id))
            .values(control_metrics=control_metrics, variant_metrics=variant_metrics)
        )

    async def conclude(
        self,
        experiment_id: str,
        winner: str,
        concluded_at: datetime,
    ) -> None:
        await self._session.execute(
            update(AdExperimentModel)
            .where(AdExperimentModel.id == uuid.UUID(experiment_id))
            .values(status="concluded", winner=winner, concluded_at=concluded_at)
        )

    async def cancel(self, experiment_id: str, concluded_at: datetime) -> None:
        await self._session.execute(
            update(AdExperimentModel)
            .where(AdExperimentModel.id == uuid.UUID(experiment_id))
            .values(status="cancelled", concluded_at=concluded_at)
        )
