"""DbKeywordFlowService — production wiring for the keyword API.

Owns session lifecycle and Celery dispatch for the generate → validate → status →
comparison flow. The API depends on this behind a swappable dependency so tests
can substitute an in-memory implementation.

Resolves the campaign's vertical/language/service/problems from the launch brief
(``campaign_id`` == brief id) when present, so the keyword engine is wired
directly into the existing campaign-creation flow; request-body fields override.
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.application.use_cases.campaign_intelligence.keywords.rank_keywords import (
    RankKeywordsUseCase,
)
from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import KeywordComparison
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.infrastructure.cie.campaign_context import (
    CampaignForbidden,
    CampaignNotFound,
    resolve_campaign_context,
)
from adcopilot.infrastructure.db.repositories.cie_keyword_repository import SqlCieKeywordRepository

logger = structlog.get_logger(__name__)

__all__ = ["CampaignForbidden", "CampaignNotFound", "DbKeywordFlowService"]


class DbKeywordFlowService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _engine(self):  # noqa: ANN202
        return create_async_engine(self._settings.DATABASE_URL)

    async def generate(
        self,
        *,
        campaign_id: str,
        user_id: str,
        account_id: str | None = None,
        vertical: str | None = None,
        language: str | None = None,
        service: str | None = None,
        problems: list[str] | None = None,
        seeds: list[str] | None = None,
    ) -> str:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session, session.begin():
                ctx = await resolve_campaign_context(
                    session,
                    campaign_id=campaign_id,
                    user_id=user_id,
                    account_id=account_id,
                    vertical=vertical,
                    language=language,
                    service=service,
                )
                run = KeywordRun(
                    campaign_id=campaign_id,
                    account_id=ctx.account_id,
                    user_id=user_id,
                    vertical=ctx.vertical,
                    language=ctx.language,
                    service=ctx.service,
                    problems=problems or [],
                    seeds=seeds or [],
                    status=KeywordRunStatus.GENERATING,
                )
                run_id = await SqlCieKeywordRepository(session).create_run(run)
        finally:
            await engine.dispose()

        from adcopilot.interfaces.worker.cie_tasks import cie_generate_keywords_task

        cie_generate_keywords_task.delay(run_id)
        logger.info("cie.keywords.generate.dispatched", run_id=run_id, campaign_id=campaign_id)
        return run_id

    async def validate(self, *, campaign_id: str, user_id: str) -> str:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session, session.begin():
                repo = SqlCieKeywordRepository(session)
                run = await repo.get_latest_run_for_campaign(campaign_id, user_id)
                if run is None or run.id is None:
                    raise CampaignNotFound("No keyword run found — generate first")
                await repo.set_run_status(run.id, KeywordRunStatus.VALIDATING)
                run_id = run.id
        finally:
            await engine.dispose()

        from adcopilot.interfaces.worker.cie_tasks import cie_validate_keywords_task

        cie_validate_keywords_task.delay(run_id)
        logger.info("cie.keywords.validate.dispatched", run_id=run_id, campaign_id=campaign_id)
        return run_id

    async def get_status(
        self, *, campaign_id: str, user_id: str
    ) -> tuple[str | None, str | None]:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                run = await SqlCieKeywordRepository(session).get_latest_run_for_campaign(
                    campaign_id, user_id
                )
                if run is None:
                    return None, None
                return run.status.value, run.id
        finally:
            await engine.dispose()

    async def comparison(
        self, *, campaign_id: str, user_id: str
    ) -> KeywordComparison | None:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                repo = SqlCieKeywordRepository(session)
                run = await repo.get_latest_run_for_campaign(campaign_id, user_id)
                if run is None or run.id is None:
                    return None
                return await RankKeywordsUseCase(repo).run(run.id)
        finally:
            await engine.dispose()
