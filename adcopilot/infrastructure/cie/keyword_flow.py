"""DbKeywordFlowService — production wiring for the keyword API.

Owns session lifecycle and Celery dispatch for the generate → validate → status →
comparison flow. The API depends on this behind a swappable dependency so tests
can substitute an in-memory implementation.

Resolves the campaign's vertical/language/service/problems from the launch brief
(``campaign_id`` == brief id) when present, so the keyword engine is wired
directly into the existing campaign-creation flow; request-body fields override.
"""

from __future__ import annotations

import uuid

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
from adcopilot.domain.campaign_intelligence.shared.vertical import Vertical
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.db.repositories.cie_keyword_repository import SqlCieKeywordRepository
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)

logger = structlog.get_logger(__name__)


class CampaignNotFound(LookupError):
    pass


class CampaignForbidden(PermissionError):
    pass


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
                resolved = await self._resolve_campaign_context(
                    session, campaign_id, user_id, account_id, vertical, language, service
                )
                run = KeywordRun(
                    campaign_id=campaign_id,
                    account_id=resolved["account_id"],
                    user_id=user_id,
                    vertical=resolved["vertical"],
                    language=language or resolved["language"],
                    service=service or resolved["service"],
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

    async def _resolve_campaign_context(
        self,
        session: AsyncSession,
        campaign_id: str,
        user_id: str,
        account_id: str | None,
        vertical: str | None,
        language: str | None,
        service: str | None,
    ) -> dict[str, str]:
        """Pull defaults from the launch brief (if any) and verify ownership."""
        brief = await self._try_get_brief(session, campaign_id, user_id)
        resolved_account = account_id or (str(brief.account_id) if brief else None)
        if resolved_account is None:
            raise CampaignNotFound(
                "account_id is required when the campaign has no launch brief"
            )

        account = await SqlGoogleAdsAccountRepository(session).get(AccountId(resolved_account))
        if account is None:
            raise CampaignNotFound("Account not found")
        if str(account.user_id) != user_id:
            raise CampaignForbidden("Account does not belong to user")

        raw_vertical = vertical or (brief.vertical if brief else None) or account.vertical
        resolved_vertical = Vertical.from_raw(raw_vertical).value.value
        resolved_language = language or (brief.language if brief else None) or "pl"
        resolved_service = service or (brief.business_description if brief else "") or ""
        return {
            "account_id": resolved_account,
            "vertical": resolved_vertical,
            "language": resolved_language,
            "service": resolved_service,
        }

    @staticmethod
    async def _try_get_brief(session: AsyncSession, campaign_id: str, user_id: str):  # noqa: ANN205
        try:
            uuid.UUID(campaign_id)
        except ValueError:
            return None
        from adcopilot.domain.launch.entities import CampaignBriefId
        from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
            SqlCampaignBriefRepository,
        )

        brief = await SqlCampaignBriefRepository(session).get(CampaignBriefId(campaign_id))
        if brief is not None and str(brief.user_id) == user_id:
            return brief
        return None
