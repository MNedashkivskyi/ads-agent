"""POST /api/website/analyze — website intelligence extraction endpoint."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from adcopilot.infrastructure.adapters.http_website_crawler import HttpWebsiteCrawlerAdapter
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.rate_limit import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/website", tags=["website"])

# Expensive (crawl + LLM extraction) — cap per IP on top of the blanket /api cap.
_ANALYZE_LIMIT = "10/minute"

_crawler = HttpWebsiteCrawlerAdapter()


class AnalyzeRequest(BaseModel):
    url: str
    vertical_id: str | None = None


class AnalyzeResponse(BaseModel):
    status: str  # "ok" | "failed" | "timeout" | "robots_blocked"
    business_name: str
    city: str
    phone: str | None
    services_detected: list[str]
    language: str
    meta_description: str


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(_ANALYZE_LIMIT)
async def analyze_website(
    request: Request,
    body: AnalyzeRequest,
    user_id: CurrentUser,
) -> AnalyzeResponse:
    """Crawl a website and extract business intelligence for the campaign wizard.

    This endpoint runs synchronously (no Celery). A homepage crawl + LLM extraction
    completes within 8 seconds for typical sites.
    """
    from adcopilot.application.services.website_intelligence_extractor import (
        WebsiteIntelligenceExtractor,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    intelligence = await _crawler.crawl(body.url)

    # Enrich with LLM if API key is configured
    settings = get_settings()
    if settings.LLM_API_KEY and intelligence.is_successful:
        try:
            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            extractor = WebsiteIntelligenceExtractor(llm)
            intelligence = await extractor.enrich(
                intelligence, vertical=body.vertical_id or "general"
            )
        except Exception as exc:
            logger.warning("website_analyze: LLM enrichment failed", error=str(exc))

    logger.info(
        "website_analyze: complete",
        url=body.url,
        status=intelligence.crawl_status,
        user_id=user_id,
    )

    return AnalyzeResponse(
        status=intelligence.crawl_status.value,
        business_name=intelligence.business_name,
        city=intelligence.city,
        phone=intelligence.primary_phone,
        services_detected=intelligence.services_detected,
        language=intelligence.language,
        meta_description=intelligence.meta_description,
    )
