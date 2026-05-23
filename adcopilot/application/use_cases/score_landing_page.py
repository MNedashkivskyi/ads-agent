"""LandingPageScoreUseCase — PageSpeed + LLM generates 3 Polish improvement recommendations."""

from __future__ import annotations

import json
import re

import structlog

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.page_analyzer import PageAnalyzer
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt
from adcopilot.domain.landing_page_score import LandingPageScore

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "landing_page_score_v1"
_SYSTEM = (
    "Jesteś ekspertem UX i SEO pomagającym polskim firmom MŚP. "
    "Odpowiadaj wyłącznie po polsku. Generuj wyłącznie poprawny JSON."
)


def _ms_label(value: float | None) -> str:
    if value is None:
        return "brak danych"
    if value >= 1000:
        return f"{value / 1000:.1f} s"
    return f"{value:.0f} ms"


def _parse_recommendations(raw: str) -> list[str]:
    match = re.search(r"\[.*?\]", raw, re.DOTALL)
    if not match:
        logger.warning("landing_page_score.bad_llm_json", raw=raw[:200])
        return []
    try:
        items = json.loads(match.group())
        return [str(i) for i in items[:3]]
    except json.JSONDecodeError:
        return []


class LandingPageScoreUseCase:
    def __init__(
        self,
        page_analyzer: PageAnalyzer,
        llm: LLMClient,
        prompt_repo: PromptVersionRepository,
    ) -> None:
        self._page_analyzer = page_analyzer
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def execute(self, url: str) -> LandingPageScore:
        """Fetch PSI score and annotate with 3 LLM-generated Polish recommendations."""
        score = await self._page_analyzer.analyze(url)

        cwv = score.core_web_vitals
        prompt_template = await get_latest_prompt(self._prompt_repo, _PROMPT_KEY)
        user_msg = prompt_template.format(
            url=url,
            performance_score=score.performance_score,
            accessibility_score=score.accessibility_score,
            seo_score=score.seo_score,
            best_practices_score=score.best_practices_score,
            mobile_friendly="Tak" if score.mobile_friendly else "Nie",
            lcp_ms=_ms_label(cwv.lcp_ms),
            fcp_ms=_ms_label(cwv.fcp_ms),
            cls_score=f"{cwv.cls_score:.3f}" if cwv.cls_score is not None else "brak danych",
            tbt_ms=_ms_label(cwv.tbt_ms),
            ttfb_ms=_ms_label(cwv.ttfb_ms),
        )

        raw = await self._llm.complete(
            system=_SYSTEM, user=user_msg, max_tokens=800, temperature=0.4
        )
        recommendations = _parse_recommendations(raw)

        # Return a new frozen instance with recommendations attached
        import dataclasses

        scored = dataclasses.replace(score, recommendations_pl=recommendations)

        logger.info(
            "landing_page_score.completed",
            url=url,
            performance=scored.performance_score,
            recommendations=len(recommendations),
        )
        return scored
