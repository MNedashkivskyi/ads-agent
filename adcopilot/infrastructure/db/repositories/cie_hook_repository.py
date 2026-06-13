"""SQL implementation of CieHookRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import (
    HookCandidate,
    HookStatus,
)
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun, HookRunStatus
from adcopilot.domain.campaign_intelligence.creatives.hook_score import HookScore
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyFinding, PolicyRisk
from adcopilot.infrastructure.db.models import (
    CieHookCandidateModel,
    CieHookSetModel,
    CieShippedAssetModel,
)


def _run_to_domain(m: CieHookSetModel) -> HookRun:
    return HookRun(
        id=str(m.id),
        campaign_id=str(m.campaign_id),
        account_id=str(m.account_id),
        user_id=m.user_id,
        vertical=m.vertical,
        language=m.language,
        service=m.service,
        problems=list(m.problems or []),
        status=HookRunStatus(m.status),
        rsa_payload=m.rsa_payload,
        error=m.error,
        created_at=m.created_at,
    )


def _candidate_to_domain(m: CieHookCandidateModel) -> HookCandidate:
    score = None
    if m.final_score is not None:
        score = HookScore(
            value=m.final_score,
            judge=m.judge_score or 0.0,
            heuristic=m.heuristic_score or 0.0,
        )
    return HookCandidate(
        id=str(m.id),
        text=m.text,
        angle=Angle(m.angle),
        surface=AdSurface(m.surface),
        policy=PolicyFinding(PolicyRisk(m.policy_risk), m.policy_reason),
        score=score,
        judge_score=m.judge_score,
        status=HookStatus(m.status),
        pinned_slot=m.pinned_slot,
    )


class SqlCieHookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, run: HookRun) -> str:
        m = CieHookSetModel()
        m.campaign_id = uuid.UUID(run.campaign_id)
        m.account_id = uuid.UUID(run.account_id)
        m.user_id = run.user_id
        m.vertical = run.vertical
        m.language = run.language
        m.service = run.service
        m.problems = list(run.problems)
        m.status = run.status.value
        self._session.add(m)
        await self._session.flush()
        run.id = str(m.id)
        return run.id

    async def get_run(self, run_id: str) -> HookRun | None:
        m = await self._session.get(CieHookSetModel, uuid.UUID(run_id))
        return _run_to_domain(m) if m else None

    async def get_latest_run_for_campaign(
        self, campaign_id: str, user_id: str
    ) -> HookRun | None:
        result = await self._session.execute(
            select(CieHookSetModel)
            .where(
                CieHookSetModel.campaign_id == uuid.UUID(campaign_id),
                CieHookSetModel.user_id == user_id,
            )
            .order_by(CieHookSetModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _run_to_domain(m) if m else None

    async def set_run_status(
        self, run_id: str, status: HookRunStatus, error: str | None = None
    ) -> None:
        m = await self._session.get(CieHookSetModel, uuid.UUID(run_id))
        if m is None:
            return
        m.status = status.value
        if error is not None:
            m.error = error[:2000]

    async def set_rsa_payload(self, run_id: str, payload: dict) -> None:
        m = await self._session.get(CieHookSetModel, uuid.UUID(run_id))
        if m is not None:
            m.rsa_payload = payload

    async def replace_candidates(
        self, run_id: str, campaign_id: str, candidates: list[HookCandidate]
    ) -> None:
        await self._session.execute(
            delete(CieHookCandidateModel).where(
                CieHookCandidateModel.set_id == uuid.UUID(run_id)
            )
        )
        for c in candidates:
            m = CieHookCandidateModel()
            m.set_id = uuid.UUID(run_id)
            m.campaign_id = uuid.UUID(campaign_id)
            self._apply(m, c)
            self._session.add(m)

    async def list_candidates(
        self, run_id: str, *, statuses: list[str] | None = None
    ) -> list[HookCandidate]:
        query = select(CieHookCandidateModel).where(
            CieHookCandidateModel.set_id == uuid.UUID(run_id)
        )
        if statuses:
            query = query.where(CieHookCandidateModel.status.in_(statuses))
        result = await self._session.execute(query)
        return [_candidate_to_domain(m) for m in result.scalars().all()]

    async def save_candidate(self, candidate: HookCandidate) -> None:
        if candidate.id is None:
            return
        m = await self._session.get(CieHookCandidateModel, uuid.UUID(candidate.id))
        if m is None:
            return
        self._apply(m, candidate)

    async def record_shipped_assets(
        self,
        *,
        account_id: str,
        customer_id: str,
        campaign_id: str | None,
        vertical: str,
        language: str,
        assets: list[HookCandidate],
    ) -> None:
        for c in assets:
            stmt = (
                pg_insert(CieShippedAssetModel)
                .values(
                    account_id=uuid.UUID(account_id),
                    customer_id=customer_id or "",
                    campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
                    asset_text=c.text,
                    angle=c.angle.value,
                    surface=c.surface.value,
                    vertical=vertical,
                    language=language,
                )
                .on_conflict_do_nothing(constraint="uq_cie_shipped_asset")
            )
            await self._session.execute(stmt)

    @staticmethod
    def _apply(m: CieHookCandidateModel, c: HookCandidate) -> None:
        m.angle = c.angle.value
        m.surface = c.surface.value
        m.text = c.text
        m.char_count = c.char_count
        m.policy_risk = c.policy.risk.value
        m.policy_reason = c.policy.reason
        m.judge_score = c.judge_score
        m.heuristic_score = c.score.heuristic if c.score else None
        m.final_score = c.score.value if c.score else None
        m.status = c.status.value
        m.pinned_slot = c.pinned_slot
