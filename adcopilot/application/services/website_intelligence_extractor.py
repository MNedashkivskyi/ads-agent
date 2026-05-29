"""LLM-powered service extraction merged with website crawler output (Task 3.2)."""

from __future__ import annotations

import json
import pathlib
import re

import structlog

from adcopilot.domain.launch.website_intelligence import WebsiteIntelligence

logger = structlog.get_logger(__name__)

_PROMPT_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "config"
    / "prompts"
    / "website_intelligence_v1.txt"
)
_MAX_CONTENT_CHARS = 12_000  # ~3000 tokens


class WebsiteIntelligenceExtractor:
    """Enriches crawler output with an LLM extraction pass.

    When the LLM call fails (network error, quota, invalid JSON), falls back
    gracefully to the raw crawler output.
    """

    def __init__(self, llm_client) -> None:
        self._llm = llm_client
        self._prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")

    async def enrich(
        self,
        crawler_result: WebsiteIntelligence,
        vertical: str = "general",
    ) -> WebsiteIntelligence:
        """Run LLM extraction and merge with crawler result.

        Returns a new WebsiteIntelligence with best-available data from both sources.
        """
        if not crawler_result.is_successful:
            return crawler_result

        # Build page content summary from crawler data
        content_parts = []
        if crawler_result.business_name:
            content_parts.append(f"Business name: {crawler_result.business_name}")
        if crawler_result.meta_description:
            content_parts.append(f"Meta description: {crawler_result.meta_description}")
        if crawler_result.og_title:
            content_parts.append(f"OG title: {crawler_result.og_title}")
        if crawler_result.services_detected:
            content_parts.append(
                f"Services detected: {', '.join(crawler_result.services_detected)}"
            )
        if crawler_result.location_text:
            content_parts.append(f"Location: {crawler_result.location_text}")
        content = "\n".join(content_parts)[:_MAX_CONTENT_CHARS]

        try:
            llm_data = await self._extract_via_llm(content, vertical)
        except Exception as exc:
            logger.warning(
                "website_intelligence_extractor: LLM failed, using raw data", error=str(exc)
            )
            return crawler_result

        return self._merge(crawler_result, llm_data)

    async def _extract_via_llm(self, content: str, vertical: str) -> dict:
        prompt = self._prompt_template.format(vertical=vertical, content=content)
        response = await self._llm.complete(
            system="You extract structured business data from website content. Return only valid JSON.",
            user=prompt,
            max_tokens=600,
            temperature=0.1,
        )
        # Strip markdown code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.MULTILINE)
        return json.loads(cleaned)

    def _merge(self, crawler: WebsiteIntelligence, llm: dict) -> WebsiteIntelligence:
        """Prefer Schema.org data from crawler, fill gaps with LLM output."""
        business_name = crawler.business_name or (llm.get("business_name") or "")
        city = crawler.city or (llm.get("city") or "")
        location_text = city if city and not crawler.location_text else crawler.location_text

        phones = list(crawler.phone_numbers)
        llm_phone = llm.get("phone")
        if llm_phone and llm_phone not in phones:
            phones.insert(0, llm_phone)

        llm_services = [s for s in (llm.get("services") or []) if isinstance(s, str)]
        combined_services = list(dict.fromkeys(llm_services + crawler.services_detected))

        return WebsiteIntelligence(
            url=crawler.url,
            crawl_status=crawler.crawl_status,
            business_name=business_name,
            location_text=location_text,
            phone_numbers=phones[:5],
            services_detected=combined_services[:15],
            language=crawler.language,
            meta_description=crawler.meta_description,
            og_title=crawler.og_title,
            schema_org_data=crawler.schema_org_data,
        )
