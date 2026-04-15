"""SQLAlchemy implementation of CampaignBriefRepo."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    LaunchStatus,
)
from adcopilot.infrastructure.db.models import LaunchBriefModel


def _model_to_domain(m: LaunchBriefModel) -> CampaignBrief:
    return CampaignBrief(
        id=CampaignBriefId(str(m.id)),
        user_id=UserId(str(m.user_id)),
        account_id=AccountId(str(m.account_id)),
        business_description=m.business_description,
        location=m.location,
        typical_customer_value=Decimal(str(m.typical_customer_value)),
        primary_action=m.primary_action,
        monthly_budget_pln=Decimal(str(m.monthly_budget_pln)),
        exclusions=list(m.exclusions or []),
        language=m.language,
        created_at=m.created_at,
        status=LaunchStatus(m.status),
        interview_step=m.interview_step,
    )


class SqlCampaignBriefRepository:
    """Persists ``CampaignBrief`` aggregates to the ``launch_briefs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, brief_id: CampaignBriefId) -> CampaignBrief | None:
        result = await self._session.execute(
            select(LaunchBriefModel).where(LaunchBriefModel.id == uuid.UUID(brief_id))
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None

    async def list_for_user(self, user_id: UserId) -> list[CampaignBrief]:
        result = await self._session.execute(
            select(LaunchBriefModel)
            .where(LaunchBriefModel.user_id == uuid.UUID(user_id))
            .order_by(LaunchBriefModel.created_at.desc())
        )
        return [_model_to_domain(m) for m in result.scalars().all()]

    async def get_active_for_user(self, user_id: UserId) -> CampaignBrief | None:
        """Return the latest COLLECTING brief for *user_id*, or None."""
        result = await self._session.execute(
            select(LaunchBriefModel)
            .where(
                LaunchBriefModel.user_id == uuid.UUID(user_id),
                LaunchBriefModel.status == LaunchStatus.COLLECTING.value,
            )
            .order_by(LaunchBriefModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None

    async def save(self, brief: CampaignBrief) -> CampaignBrief:
        """Upsert *brief* and return the persisted entity."""
        m = await self._session.get(LaunchBriefModel, uuid.UUID(brief.id))
        if m is None:
            m = LaunchBriefModel(id=uuid.UUID(brief.id))
            self._session.add(m)

        m.user_id = uuid.UUID(brief.user_id)
        m.account_id = uuid.UUID(brief.account_id)
        m.business_description = brief.business_description
        m.location = brief.location
        m.typical_customer_value = brief.typical_customer_value  # type: ignore[assignment]
        m.primary_action = brief.primary_action
        m.monthly_budget_pln = brief.monthly_budget_pln  # type: ignore[assignment]
        m.exclusions = brief.exclusions
        m.language = brief.language
        m.status = brief.status.value
        m.interview_step = brief.interview_step
        m.created_at = brief.created_at

        await self._session.flush()
        return brief

    async def update_status(
        self, brief_id: CampaignBriefId, status: LaunchStatus
    ) -> None:
        m = await self._session.get(LaunchBriefModel, uuid.UUID(brief_id))
        if m is not None:
            m.status = status.value
            await self._session.flush()
