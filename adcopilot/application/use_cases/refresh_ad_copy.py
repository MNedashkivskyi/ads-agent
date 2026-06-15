"""AdCopyRefreshUseCase — LLM generates 3 RSA variants for AD_FATIGUE / WEAK_RSA_STRENGTH."""

from __future__ import annotations

import json
import re

import structlog

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt
from adcopilot.domain.ad_copy_proposal import AdCopyProposal
from adcopilot.domain.recommendation import Recommendation

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "ad_copy_refresh_v1"
_SYSTEM = (
    "Jesteś ekspertem Google Ads pomagającym polskim właścicielom firm MŚP. "
    "Odpowiadaj wyłącznie po polsku. Generuj wyłącznie poprawny JSON."
)
_MAX_HEADLINE = 30
_MAX_DESCRIPTION = 90
_NUM_VARIANTS = 3


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def _parse_proposals(raw: str, final_url: str) -> list[AdCopyProposal]:
    """Extract JSON array from LLM response and build AdCopyProposal list."""
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in LLM response: {raw[:200]}")
    data = json.loads(match.group())
    proposals = []
    for item in data[:_NUM_VARIANTS]:
        headlines = [_truncate(h, _MAX_HEADLINE) for h in item.get("headlines", [])[:3]]
        descriptions = [_truncate(d, _MAX_DESCRIPTION) for d in item.get("descriptions", [])[:2]]
        proposals.append(
            AdCopyProposal(headlines=headlines, descriptions=descriptions, final_url=final_url)
        )
    return proposals


class AdCopyRefreshUseCase:
    def __init__(self, llm: LLMClient, prompt_repo: PromptVersionRepository) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def execute(self, recommendation: Recommendation) -> list[AdCopyProposal]:
        """Generate 3 RSA variants for a AD_FATIGUE or WEAK_RSA_STRENGTH recommendation."""
        ev = recommendation.evidence
        proposals = await self.execute_for_ad(
            campaign_name=ev.get("campaign_name", ""),
            vertical=ev.get("vertical", "ogólna"),
            keyword_themes=ev.get("keyword_themes", ""),
            headlines=ev.get("headlines", []),
            descriptions=ev.get("descriptions", []),
            final_url=ev.get("final_url", ""),
        )

        if len(proposals) < _NUM_VARIANTS:
            logger.warning(
                "ad_copy_refresh.too_few_variants",
                got=len(proposals),
                expected=_NUM_VARIANTS,
                rec_id=str(recommendation.id),
            )

        logger.info(
            "ad_copy_refresh.generated",
            account_id=str(recommendation.account_id),
            rec_id=str(recommendation.id),
            variants=len(proposals),
        )
        return proposals

    async def execute_for_ad(
        self,
        *,
        campaign_name: str,
        vertical: str = "ogólna",
        keyword_themes: str = "",
        headlines: list[str] | None = None,
        descriptions: list[str] | None = None,
        final_url: str = "",
    ) -> list[AdCopyProposal]:
        """Generate Polish RSA variants for an existing ad on demand.

        This is the recommendation-independent entry point used by the on-demand
        optimization endpoint (T2.2): the caller passes the ad's current copy and
        context directly, so variant generation is no longer tied to an
        AD_FATIGUE recommendation firing. Uses the versioned ``ad_copy_refresh_v1``
        prompt and returns Polish output.
        """
        existing_headlines = ", ".join(headlines or [])
        existing_descriptions = ", ".join(descriptions or [])

        prompt_template = await get_latest_prompt(self._prompt_repo, _PROMPT_KEY)
        user_msg = prompt_template.format(
            campaign_name=campaign_name,
            vertical=vertical,
            keyword_themes=keyword_themes,
            existing_headlines=existing_headlines or "(brak)",
            existing_descriptions=existing_descriptions or "(brak)",
        )

        raw = await self._llm.complete(
            system=_SYSTEM, user=user_msg, max_tokens=1200, temperature=0.7
        )
        return _parse_proposals(raw, final_url)
