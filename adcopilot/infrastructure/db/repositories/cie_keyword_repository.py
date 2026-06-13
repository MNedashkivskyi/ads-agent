"""SQL implementation of CieKeywordRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    KeywordScore,
    SearchVolume,
)
from adcopilot.infrastructure.db.models import CieKeywordCandidateModel, CieKeywordRunModel


def _run_to_domain(m: CieKeywordRunModel) -> KeywordRun:
    return KeywordRun(
        id=str(m.id),
        campaign_id=str(m.campaign_id),
        account_id=str(m.account_id),
        user_id=m.user_id,
        vertical=m.vertical,
        language=m.language,
        service=m.service,
        problems=list(m.problems or []),
        seeds=list(m.seeds or []),
        status=KeywordRunStatus(m.status),
        error=m.error,
        created_at=m.created_at,
    )


def _candidate_to_domain(m: CieKeywordCandidateModel) -> KeywordCandidate:
    volume: SearchVolume | None = None
    if m.monthly_searches is not None:
        volume = SearchVolume(
            monthly_searches=m.monthly_searches,
            competition=m.competition or "UNKNOWN",
            cpc_low_micros=m.cpc_low_micros or 0,
            cpc_high_micros=m.cpc_high_micros or 0,
            is_bucketed=m.is_bucketed,
        )
    score = KeywordScore(m.score) if m.score is not None else None
    return KeywordCandidate(
        id=str(m.id),
        phrase=m.phrase,
        intent=KeywordIntent(m.intent),
        volume=volume,
        score=score,
        status=KeywordStatus(m.status),
        source=m.source,
        reasoning=m.reasoning,
    )


class SqlCieKeywordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, run: KeywordRun) -> str:
        m = CieKeywordRunModel()
        m.campaign_id = uuid.UUID(run.campaign_id)
        m.account_id = uuid.UUID(run.account_id)
        m.user_id = run.user_id
        m.vertical = run.vertical
        m.language = run.language
        m.service = run.service
        m.problems = list(run.problems)
        m.seeds = list(run.seeds)
        m.status = run.status.value
        self._session.add(m)
        await self._session.flush()
        run.id = str(m.id)
        return run.id

    async def get_run(self, run_id: str) -> KeywordRun | None:
        m = await self._session.get(CieKeywordRunModel, uuid.UUID(run_id))
        return _run_to_domain(m) if m else None

    async def get_latest_run_for_campaign(
        self, campaign_id: str, user_id: str
    ) -> KeywordRun | None:
        result = await self._session.execute(
            select(CieKeywordRunModel)
            .where(
                CieKeywordRunModel.campaign_id == uuid.UUID(campaign_id),
                CieKeywordRunModel.user_id == user_id,
            )
            .order_by(CieKeywordRunModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _run_to_domain(m) if m else None

    async def set_run_status(
        self, run_id: str, status: KeywordRunStatus, error: str | None = None
    ) -> None:
        m = await self._session.get(CieKeywordRunModel, uuid.UUID(run_id))
        if m is None:
            return
        m.status = status.value
        if error is not None:
            m.error = error[:2000]

    async def replace_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        await self._session.execute(
            delete(CieKeywordCandidateModel).where(
                CieKeywordCandidateModel.run_id == uuid.UUID(run_id)
            )
        )
        await self.add_candidates(run_id, campaign_id, candidates)

    async def add_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        existing = await self._existing_phrases(run_id)
        for c in candidates:
            if c.phrase.strip().lower() in existing:
                continue
            existing.add(c.phrase.strip().lower())
            m = CieKeywordCandidateModel()
            m.run_id = uuid.UUID(run_id)
            m.campaign_id = uuid.UUID(campaign_id)
            m.phrase = c.phrase
            m.intent = c.intent.value
            m.source = c.source
            m.reasoning = c.reasoning
            m.status = c.status.value
            self._apply_volume_columns(m, c)
            self._session.add(m)

    async def list_candidates(
        self, run_id: str, *, statuses: list[str] | None = None
    ) -> list[KeywordCandidate]:
        query = select(CieKeywordCandidateModel).where(
            CieKeywordCandidateModel.run_id == uuid.UUID(run_id)
        )
        if statuses:
            query = query.where(CieKeywordCandidateModel.status.in_(statuses))
        result = await self._session.execute(query)
        return [_candidate_to_domain(m) for m in result.scalars().all()]

    async def save_candidate(self, candidate: KeywordCandidate) -> None:
        if candidate.id is None:
            return
        m = await self._session.get(CieKeywordCandidateModel, uuid.UUID(candidate.id))
        if m is None:
            return
        m.status = candidate.status.value
        if candidate.score is not None:
            m.score = candidate.score.value
        self._apply_volume_columns(m, candidate)

    async def list_phrases_for_campaign(self, campaign_id: str) -> set[str]:
        result = await self._session.execute(
            select(CieKeywordCandidateModel.phrase).where(
                CieKeywordCandidateModel.campaign_id == uuid.UUID(campaign_id)
            )
        )
        return {row[0].strip().lower() for row in result.all()}

    async def _existing_phrases(self, run_id: str) -> set[str]:
        result = await self._session.execute(
            select(CieKeywordCandidateModel.phrase).where(
                CieKeywordCandidateModel.run_id == uuid.UUID(run_id)
            )
        )
        return {row[0].strip().lower() for row in result.all()}

    @staticmethod
    def _apply_volume_columns(m: CieKeywordCandidateModel, c: KeywordCandidate) -> None:
        if c.volume is not None:
            m.monthly_searches = c.volume.monthly_searches
            m.competition = c.volume.competition
            m.cpc_low_micros = c.volume.cpc_low_micros
            m.cpc_high_micros = c.volume.cpc_high_micros
            m.is_bucketed = c.volume.is_bucketed
        if c.score is not None:
            m.score = c.score.value
