"""Celery tasks for the Campaign Intelligence Engine.

Kept in a dedicated module (registered via the Celery ``include`` list) so the
large legacy ``tasks.py`` stays focused. Covers keyword generation/validation,
hook generation/finalization, nightly performance ingest, search-term harvesting,
and weight recomputation.
"""

from __future__ import annotations

import asyncio

import structlog

from adcopilot.interfaces.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Keyword track
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.cie_tasks.cie_generate_keywords_task",
    max_retries=2,
    default_retry_delay=15,
)
def cie_generate_keywords_task(run_id: str) -> dict[str, object]:
    """Generate keyword candidates for a persisted run."""
    return asyncio.run(_run_generate_keywords(run_id))


async def _run_generate_keywords(run_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.campaign_intelligence.keywords.generate_keyword_candidates import (  # noqa: E501
        GenerateKeywordCandidatesUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.cie.wiring import build_keyword_generator
    from adcopilot.infrastructure.db.repositories.cie_keyword_repository import (
        SqlCieKeywordRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCieKeywordRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                logger.warning("cie.generate.run_missing", run_id=run_id)
                return {"run_id": run_id, "status": "missing"}
            generator = build_keyword_generator(settings, SqlPromptVersionRepository(session))
            use_case = GenerateKeywordCandidatesUseCase(generator, repo)
            await use_case.run(run)

            # Optional, flag-gated reality-grounded expansion (Phase 2).
            if settings.ENABLE_KEYWORD_EXPANSION:
                from adcopilot.application.use_cases.campaign_intelligence.keywords.expand_keywords import (  # noqa: E501
                    ExpandKeywordsUseCase,
                )
                from adcopilot.infrastructure.cie.wiring import build_dataforseo_adapter

                expander = build_dataforseo_adapter(settings)
                await ExpandKeywordsUseCase(
                    expander,
                    repo,
                    enabled=settings.ENABLE_KEYWORD_EXPANSION,
                    max_requests=settings.KEYWORD_EXPANSION_MAX_REQUESTS,
                ).run(run)
            return {"run_id": run_id, "status": run.status.value}
    except Exception as exc:  # noqa: BLE001 — record failure, surface status
        logger.error("cie.generate.failed", run_id=run_id, error=str(exc))
        await _mark_run_failed(settings, run_id, str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.cie_tasks.cie_validate_keywords_task",
    max_retries=3,
    default_retry_delay=30,
)
def cie_validate_keywords_task(run_id: str) -> dict[str, object]:
    """Validate keyword volumes for a run (cache → KP → DataForSEO)."""
    return asyncio.run(_run_validate_keywords(run_id))


async def _run_validate_keywords(run_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
        ValidateKeywordVolumesUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.cie.wiring import (
        build_dataforseo_adapter,
        build_kp_volume_adapter,
        build_volume_cache,
    )
    from adcopilot.infrastructure.db.repositories.cie_keyword_repository import (
        SqlCieKeywordRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCieKeywordRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                logger.warning("cie.validate.run_missing", run_id=run_id)
                return {"run_id": run_id, "status": "missing"}

            account_repo = SqlGoogleAdsAccountRepository(session)
            creds_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            account = await account_repo.get(AccountId(run.account_id))
            credentials = await creds_repo.get(AccountId(run.account_id))
            refresh_token = credentials.refresh_token if credentials else None
            customer_id = account.customer_id if account else None

            use_case = ValidateKeywordVolumesUseCase(
                cache=build_volume_cache(settings),
                primary=build_kp_volume_adapter(settings),
                fallback=build_dataforseo_adapter(settings),
                repo=repo,
                min_viable_volume=settings.KEYWORD_MIN_VIABLE_VOLUME,
            )
            await use_case.run(run, refresh_token=refresh_token, customer_id=customer_id)
            return {"run_id": run_id, "status": run.status.value}
    except Exception as exc:  # noqa: BLE001
        logger.error("cie.validate.failed", run_id=run_id, error=str(exc))
        await _mark_run_failed(settings, run_id, str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()


async def _mark_run_failed(settings: object, run_id: str, error: str) -> None:
    """Best-effort: flip the run to failed in its own transaction."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.campaign_intelligence.keywords.keyword_run import KeywordRunStatus
    from adcopilot.infrastructure.db.repositories.cie_keyword_repository import (
        SqlCieKeywordRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)  # type: ignore[attr-defined]
    try:
        async with AsyncSession(engine) as session, session.begin():
            await SqlCieKeywordRepository(session).set_run_status(
                run_id, KeywordRunStatus.FAILED, error
            )
    except Exception:  # noqa: BLE001 — never raise from the failure handler
        logger.warning("cie.mark_failed.error", run_id=run_id)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Creative (hook) track
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.cie_tasks.cie_generate_hooks_task",
    max_retries=2,
    default_retry_delay=15,
)
def cie_generate_hooks_task(run_id: str) -> dict[str, object]:
    """Generate hook candidates across angles for a persisted hook run."""
    return asyncio.run(_run_generate_hooks(run_id))


async def _run_generate_hooks(run_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.campaign_intelligence.creatives.generate_hooks import (
        GenerateHooksUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.cie.wiring import build_hook_generator
    from adcopilot.infrastructure.db.repositories.cie_hook_repository import SqlCieHookRepository
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCieHookRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                return {"run_id": run_id, "status": "missing"}
            generator = build_hook_generator(settings, SqlPromptVersionRepository(session))
            await GenerateHooksUseCase(generator, repo).run(run)
            return {"run_id": run_id, "status": run.status.value}
    except Exception as exc:  # noqa: BLE001
        logger.error("cie.hooks.generate.failed", run_id=run_id, error=str(exc))
        await _mark_hook_run_failed(settings, run_id, str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.cie_tasks.cie_select_hooks_task",
    max_retries=2,
    default_retry_delay=15,
)
def cie_select_hooks_task(run_id: str) -> dict[str, object]:
    """Judge + select the top hooks per surface with angle diversity."""
    return asyncio.run(_run_select_hooks(run_id))


async def _run_select_hooks(run_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.campaign_intelligence.creatives.select_hooks import (
        SelectHooksUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.cie.wiring import build_hook_judge
    from adcopilot.infrastructure.db.repositories.cie_hook_repository import SqlCieHookRepository
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCieHookRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                return {"run_id": run_id, "status": "missing"}
            judge = build_hook_judge(settings, SqlPromptVersionRepository(session))
            selected = await SelectHooksUseCase(judge, repo).run(run)
            return {"run_id": run_id, "selected": len(selected)}
    except Exception as exc:  # noqa: BLE001
        logger.error("cie.hooks.select.failed", run_id=run_id, error=str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.cie_tasks.cie_finalize_hooks_task",
    max_retries=1,
    default_retry_delay=15,
)
def cie_finalize_hooks_task(run_id: str) -> dict[str, object]:
    """Assemble the RSA payload and tag every shipped asset by angle."""
    return asyncio.run(_run_finalize_hooks(run_id))


async def _run_finalize_hooks(run_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.campaign_intelligence.creatives.finalize_hook_set import (
        FinalizeHookSetUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.cie_hook_repository import SqlCieHookRepository
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCieHookRepository(session)
            run = await repo.get_run(run_id)
            if run is None:
                return {"run_id": run_id, "status": "missing"}
            account = await SqlGoogleAdsAccountRepository(session).get(AccountId(run.account_id))
            customer_id = account.customer_id if account else ""
            payload = await FinalizeHookSetUseCase(repo).run(run, customer_id=customer_id)
            return {"run_id": run_id, "status": "finalized", "headlines": len(payload.get("headlines", []))}
    except Exception as exc:  # noqa: BLE001
        logger.error("cie.hooks.finalize.failed", run_id=run_id, error=str(exc))
        return {"run_id": run_id, "status": "failed", "error": str(exc)}
    finally:
        await engine.dispose()


async def _mark_hook_run_failed(settings: object, run_id: str, error: str) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRunStatus
    from adcopilot.infrastructure.db.repositories.cie_hook_repository import SqlCieHookRepository

    engine = create_async_engine(settings.DATABASE_URL)  # type: ignore[attr-defined]
    try:
        async with AsyncSession(engine) as session, session.begin():
            await SqlCieHookRepository(session).set_run_status(
                run_id, HookRunStatus.FAILED, error
            )
    except Exception:  # noqa: BLE001
        logger.warning("cie.hooks.mark_failed.error", run_id=run_id)
    finally:
        await engine.dispose()
