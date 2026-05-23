"""Landing page score API endpoints — GET score (rate-limited)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.rate_limit import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["landing-page"])

# 5 PSI calls per minute per user — PSI free tier is 400 req/100s globally;
# this prevents a single user from exhausting the quota.
_SCORE_LIMIT = "5/minute"


class CoreWebVitalsResponse(BaseModel):
    lcp_ms: float | None = None
    fcp_ms: float | None = None
    cls_score: float | None = None
    ttfb_ms: float | None = None
    tbt_ms: float | None = None
    speed_index_ms: float | None = None


class LandingPageScoreResponse(BaseModel):
    url: str
    performance_score: int
    accessibility_score: int
    seo_score: int
    best_practices_score: int
    mobile_friendly: bool
    core_web_vitals: CoreWebVitalsResponse
    recommendations_pl: list[str]
    scored_at: str


@router.get("/{user_id}/landing-page/score", response_model=LandingPageScoreResponse)
@limiter.limit(_SCORE_LIMIT)
async def get_landing_page_score(
    request: Request,
    user_id: str,
    url: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LandingPageScoreResponse:
    """Fetch PageSpeed score + 3 Polish improvement recommendations for the given URL."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.score_landing_page import LandingPageScoreUseCase
    from adcopilot.domain.exceptions import PageAnalyzerError
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.infrastructure.landing_page.pagespeed_adapter import PageSpeedAdapter
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    adapter = PageSpeedAdapter(api_key=settings.PAGESPEED_API_KEY)
    llm = AnthropicClient(api_key=settings.LLM_API_KEY)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            prompt_repo = SqlPromptVersionRepository(session)
            use_case = LandingPageScoreUseCase(
                page_analyzer=adapter, llm=llm, prompt_repo=prompt_repo
            )
            try:
                score = await use_case.execute(url)
            except PageAnalyzerError as exc:
                raise HTTPException(status_code=502, detail=f"PageSpeed API error: {exc}") from exc
    finally:
        await engine.dispose()

    cwv = score.core_web_vitals
    return LandingPageScoreResponse(
        url=score.url,
        performance_score=score.performance_score,
        accessibility_score=score.accessibility_score,
        seo_score=score.seo_score,
        best_practices_score=score.best_practices_score,
        mobile_friendly=score.mobile_friendly,
        core_web_vitals=CoreWebVitalsResponse(
            lcp_ms=cwv.lcp_ms,
            fcp_ms=cwv.fcp_ms,
            cls_score=cwv.cls_score,
            ttfb_ms=cwv.ttfb_ms,
            tbt_ms=cwv.tbt_ms,
            speed_index_ms=cwv.speed_index_ms,
        ),
        recommendations_pl=score.recommendations_pl,
        scored_at=score.scored_at.isoformat(),
    )
