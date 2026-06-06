from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings
from adcopilot.logging_config import configure_logging
from adcopilot.middleware import RequestIdMiddleware
from adcopilot.observability import init_sentry
from adcopilot.observability.fastapi_middleware import SentryContextMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    settings = get_settings()
    logger.info("adcopilot starting", env=settings.ENV)

    yield

    logger.info("adcopilot shutting down")


def create_app() -> FastAPI:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    from adcopilot.interfaces.api.account_structure import router as account_structure_router
    from adcopilot.interfaces.api.ad_proposals import router as ad_proposals_router
    from adcopilot.interfaces.api.admin import router as admin_router
    from adcopilot.interfaces.api.audiences import router as audiences_router
    from adcopilot.interfaces.api.auth import router as auth_router
    from adcopilot.interfaces.api.billing import router as billing_router
    from adcopilot.interfaces.api.conversion_tracking import router as conversion_tracking_router
    from adcopilot.interfaces.api.conversion_tracking_guide import (
        router as conversion_tracking_guide_router,
    )
    from adcopilot.interfaces.api.dashboard import router as dashboard_router
    from adcopilot.interfaces.api.debug import router as debug_router
    from adcopilot.interfaces.api.digest import router as digest_router
    from adcopilot.interfaces.api.causal_experiments import router as causal_experiments_router
    from adcopilot.interfaces.api.experiments import router as experiments_router
    from adcopilot.interfaces.api.shopping import router as shopping_router
    from adcopilot.interfaces.api.spend_safety import router as spend_safety_router
    from adcopilot.interfaces.api.insights import router as insights_router
    from adcopilot.interfaces.api.landing_page import router as landing_page_router
    from adcopilot.interfaces.api.launch import api_router as launch_api_router
    from adcopilot.interfaces.api.launch import router as launch_router
    from adcopilot.interfaces.api.launch_error_recovery import (
        router as launch_error_recovery_router,
    )
    from adcopilot.interfaces.api.notifications import router as notifications_router
    from adcopilot.interfaces.api.oauth import router as oauth_router
    from adcopilot.interfaces.api.pmax import router as pmax_router
    from adcopilot.interfaces.api.measurement import router as measurement_router
    from adcopilot.interfaces.api.proposal_editor import router as proposal_editor_router
    from adcopilot.interfaces.api.qa import router as qa_router
    from adcopilot.interfaces.api.qs_improvement import router as qs_improvement_router
    from adcopilot.interfaces.api.quality_score import router as quality_score_router
    from adcopilot.interfaces.api.reports import router as reports_router
    from adcopilot.interfaces.api.search_terms import router as search_terms_router
    from adcopilot.interfaces.api.seasonality import router as seasonality_router
    from adcopilot.interfaces.api.snapshots import router as snapshots_router
    from adcopilot.interfaces.api.users import router as users_router
    from adcopilot.interfaces.api.website import router as website_router
    from adcopilot.rate_limit import limiter
    from adcopilot.security import PathPrefixRateLimitMiddleware

    # Initialise Sentry before the ASGI app is built so FastAPI/Starlette
    # integrations hook into the request lifecycle.  Idempotent.
    init_sentry(component="api")

    application = FastAPI(title="AdsWise", version="0.1.0", lifespan=lifespan)
    # Rate limiting — must be registered before SlowAPIMiddleware is added.
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    application.add_middleware(SlowAPIMiddleware)
    # Path-prefix rate limits envelope the per-endpoint slowapi decorators.
    # Configured limits: /oauth/* 10/min, /api/* 60/min, /webhooks/* 100/min.
    # See adcopilot/security/rate_limiting.py.
    application.add_middleware(PathPrefixRateLimitMiddleware, storage_uri=get_settings().REDIS_URL)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(SentryContextMiddleware)

    # CORS — origin allow-list.  In production the ONLY accepted origin is
    # the canonical web domain set via APP_URL (e.g. https://adswise.xyz).
    # No wildcards.  In non-production environments we additionally allow
    # localhost so the Next.js dev server can talk to a local API.
    from fastapi.middleware.cors import CORSMiddleware

    from adcopilot.security import build_cors_allowed_origins

    settings = get_settings()
    allowed_origins = build_cors_allowed_origins(settings)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        # Do NOT use allow_origin_regex — any regex here effectively widens
        # the allow-list and can regress into a de-facto wildcard.
        allow_credentials=True,
        # Explicit methods/headers — no "*" even though the ASGI CORS
        # middleware would otherwise accept it.  If a new method or header
        # is required, it must be added here deliberately.
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.include_router(auth_router)
    application.include_router(oauth_router)
    application.include_router(snapshots_router)
    application.include_router(digest_router)
    application.include_router(users_router)
    application.include_router(billing_router)
    application.include_router(debug_router)
    application.include_router(launch_router)
    application.include_router(launch_api_router)
    application.include_router(website_router)
    application.include_router(dashboard_router)
    application.include_router(notifications_router)
    application.include_router(conversion_tracking_router)
    application.include_router(conversion_tracking_guide_router)
    application.include_router(launch_error_recovery_router)
    application.include_router(proposal_editor_router)
    application.include_router(experiments_router)
    application.include_router(causal_experiments_router)
    application.include_router(spend_safety_router)
    application.include_router(shopping_router)
    application.include_router(search_terms_router)
    application.include_router(ad_proposals_router)
    application.include_router(landing_page_router)
    application.include_router(qa_router)
    application.include_router(insights_router)
    application.include_router(admin_router)
    application.include_router(pmax_router)
    application.include_router(quality_score_router)
    application.include_router(qs_improvement_router)
    application.include_router(measurement_router)
    application.include_router(audiences_router)
    application.include_router(reports_router)
    application.include_router(account_structure_router)
    application.include_router(seasonality_router)

    @application.get("/health")
    async def health() -> JSONResponse:
        settings = get_settings()
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        try:
            async with AsyncSession(engine) as session:
                await session.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:
            logger.warning("health check db failed", error=str(exc))
            db_status = "error"
        finally:
            await engine.dispose()

        status_code = 200 if db_status == "ok" else 503
        return JSONResponse(
            status_code=status_code,
            content={"status": "ok" if db_status == "ok" else "degraded", "db": db_status},
        )

    return application


app = create_app()
