"""DbKeywordFlowService — production wiring for the keyword API.

Owns session lifecycle and Celery dispatch for the generate → validate → status →
comparison flow. The API depends on this behind a swappable dependency so tests
can substitute an in-memory implementation.

Resolves the campaign's vertical/language/service from the account it belongs to
(the launch-brief fallback was removed in the optimization pivot, T2.1); the
keyword engine runs against an existing campaign and request-body fields
override the resolved defaults.
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
from adcopilot.infrastructure.db.repositories.cie_search_term_repository import (
    SqlCieSearchTermRepository,
)

logger = structlog.get_logger(__name__)

__all__ = ["CampaignForbidden", "CampaignNotFound", "DbKeywordFlowService"]


class DbKeywordFlowService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _engine(self):  # noqa: ANN202
        return create_async_engine(self._settings.DATABASE_URL)

    async def analyze(
        self,
        *,
        campaign_id: str,
        user_id: str,
        account_id: str | None = None,
        vertical: str | None = None,
        language: str | None = None,
        service: str | None = None,
        problems: list[str] | None = None,
    ) -> KeywordComparison:
        """Synchronous generate → validate → rank, returning the comparison.

        Runs entirely in-request (no Celery, no polling), so it cannot hang
        silently waiting on a worker. The LLM call happens outside any DB
        transaction; only the bounded volume lookups run inside a short
        transaction. Used by the launch-wizard keyword step.
        """
        from adcopilot.application.use_cases.campaign_intelligence.keywords.generate_keyword_candidates import (  # noqa: E501
            DEFAULT_TOTAL_SLOTS,
            GenerateKeywordCandidatesUseCase,
        )
        from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
            ValidateKeywordVolumesUseCase,
        )
        from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
            KeywordCandidate,
        )
        from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
            KEYWORD_INTENT_DIMENSION,
            KeywordIntent,
        )
        from adcopilot.domain.campaign_intelligence.shared import dimension_selector
        from adcopilot.domain.campaign_intelligence.shared.learned_weights import (
            weights_from_performance,
        )
        from adcopilot.domain.entities import AccountId
        from adcopilot.infrastructure.cie.wiring import (
            build_dataforseo_adapter,
            build_keyword_generator,
            build_kp_volume_adapter,
            build_volume_cache,
        )
        from adcopilot.infrastructure.db.repositories.cie_dimension_performance_repository import (  # noqa: E501
            SqlCieDimensionPerformanceRepository,
        )
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
            SqlOAuthCredentialsRepository,
        )

        settings = self._settings
        engine = self._engine()
        try:
            # --- tx1: resolve context, create run, read learned + credentials ---
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
                account = await SqlGoogleAdsAccountRepository(session).get(
                    AccountId(ctx.account_id)
                )
                creds = await SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                ).get(AccountId(ctx.account_id))
                refresh_token = creds.refresh_token if creds else None
                customer_id = account.customer_id if account else None
                learned = await SqlCieDimensionPerformanceRepository(session).get_map(
                    vertical=ctx.vertical,
                    dimension=KEYWORD_INTENT_DIMENSION,
                    language=ctx.language,
                )
                harvested = await SqlCieSearchTermRepository(session).list_promotion_terms(
                    ctx.account_id, limit=25
                )
                run = KeywordRun(
                    campaign_id=campaign_id,
                    account_id=ctx.account_id,
                    user_id=user_id,
                    vertical=ctx.vertical,
                    language=ctx.language,
                    service=service or ctx.service,
                    problems=problems or [],
                    seeds=harvested,
                    status=KeywordRunStatus.GENERATING,
                )
                run_id = await SqlCieKeywordRepository(session).create_run(run)

            # --- generate: LLM call OUTSIDE any DB transaction ---
            allocation = dimension_selector.allocate(
                DEFAULT_TOTAL_SLOTS, [i.value for i in KeywordIntent], learned
            )
            merged_problems = GenerateKeywordCandidatesUseCase._merge_seeds(
                run.problems, run.seeds
            )
            generator = build_keyword_generator(settings)
            generated = await generator.generate(
                service=run.service,
                vertical=run.vertical,
                problems=merged_problems,
                intent_allocation=allocation,
                language=run.language,
            )
            candidates = [
                KeywordCandidate(
                    phrase=g.phrase,
                    intent=KeywordIntent(g.intent),
                    reasoning=g.reasoning,
                    source="llm",
                )
                for g in generated
            ]

            # --- tx2: persist generated candidates (short) ---
            async with AsyncSession(engine) as session, session.begin():
                repo = SqlCieKeywordRepository(session)
                await repo.replace_candidates(run_id, run.campaign_id, candidates)
                await repo.set_run_status(run_id, KeywordRunStatus.GENERATED)

            # --- tx3: validate volumes (bounded external calls) keep_all ---
            async with AsyncSession(engine) as session, session.begin():
                repo = SqlCieKeywordRepository(session)
                run2 = await repo.get_run(run_id)
                if run2 is not None:
                    await ValidateKeywordVolumesUseCase(
                        cache=build_volume_cache(settings),
                        primary=build_kp_volume_adapter(settings),
                        fallback=build_dataforseo_adapter(settings),
                        repo=repo,
                        min_viable_volume=settings.KEYWORD_MIN_VIABLE_VOLUME,
                        keep_all=True,
                    ).run(run2, refresh_token=refresh_token, customer_id=customer_id)

            # --- tx4: rank (read) ---
            async with AsyncSession(engine) as session:
                repo = SqlCieKeywordRepository(session)
                weights = weights_from_performance(learned)
                return await RankKeywordsUseCase(repo).run(
                    run_id, learned_weights=weights, performance=learned
                )
        finally:
            await engine.dispose()

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
                # Phase 5.3 — feed harvested winning terms back as extra seeds.
                merged_seeds = list(seeds or [])
                harvested = await SqlCieSearchTermRepository(session).list_promotion_terms(
                    ctx.account_id, limit=25
                )
                merged_seeds.extend(harvested)
                run = KeywordRun(
                    campaign_id=campaign_id,
                    account_id=ctx.account_id,
                    user_id=user_id,
                    vertical=ctx.vertical,
                    language=ctx.language,
                    service=ctx.service,
                    problems=problems or [],
                    seeds=merged_seeds,
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
                # Phase 6 — rank with learned intent-weights for the vertical.
                from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
                    KEYWORD_INTENT_DIMENSION,
                )
                from adcopilot.domain.campaign_intelligence.shared.learned_weights import (
                    weights_from_performance,
                )
                from adcopilot.infrastructure.db.repositories.cie_dimension_performance_repository import (  # noqa: E501
                    SqlCieDimensionPerformanceRepository,
                )

                learned = await SqlCieDimensionPerformanceRepository(session).get_map(
                    vertical=run.vertical,
                    dimension=KEYWORD_INTENT_DIMENSION,
                    language=run.language,
                )
                weights = weights_from_performance(learned)
                return await RankKeywordsUseCase(repo).run(
                    run.id, learned_weights=weights, performance=learned
                )
        finally:
            await engine.dispose()

    async def get_harvest(self, *, campaign_id: str, user_id: str) -> dict | None:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                account_id = await self._account_for_campaign(session, campaign_id, user_id)
                if account_id is None:
                    return None
                repo = SqlCieSearchTermRepository(session)
                return {
                    "promotions": await repo.list_proposals(account_id, kind="promote"),
                    "negatives": await repo.list_proposals(account_id, kind="negative"),
                }
        finally:
            await engine.dispose()

    async def trigger_harvest(self, *, campaign_id: str, user_id: str) -> str:
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session:
                account_id = await self._account_for_campaign(session, campaign_id, user_id)
                if account_id is None:
                    raise CampaignNotFound("No account found for campaign")
        finally:
            await engine.dispose()

        from adcopilot.interfaces.worker.cie_tasks import cie_harvest_search_terms_task

        cie_harvest_search_terms_task.delay(account_id)
        return account_id

    async def adopt_proposal(
        self, *, campaign_id: str, user_id: str, term: str, kind: str, decision: str
    ) -> bool:
        status = "adopted" if decision == "adopt" else "dismissed"
        engine = self._engine()
        try:
            async with AsyncSession(engine) as session, session.begin():
                account_id = await self._account_for_campaign(session, campaign_id, user_id)
                if account_id is None:
                    raise CampaignNotFound("No account found for campaign")
                return await SqlCieSearchTermRepository(session).set_proposal_status(
                    account_id, term, kind, status
                )
        finally:
            await engine.dispose()

    async def _account_for_campaign(
        self, session: AsyncSession, campaign_id: str, user_id: str
    ) -> str | None:
        run = await SqlCieKeywordRepository(session).get_latest_run_for_campaign(
            campaign_id, user_id
        )
        return run.account_id if run else None
