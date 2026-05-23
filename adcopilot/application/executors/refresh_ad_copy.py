"""Executor: create 3 new RSAs, enable them, pause lowest-CTR existing ad."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.refresh_ad_copy import AdCopyRefreshUseCase
from adcopilot.domain.recommendation import Recommendation, RecommendationKind

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


class AdCopyRefreshExecutor:
    """Executes AD_FATIGUE / WEAK_RSA_STRENGTH by creating 3 new RSAs and pausing the worst existing ad."""

    kind = RecommendationKind.AD_FATIGUE

    def __init__(self, llm: LLMClient, prompt_repo: PromptVersionRepository) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    @classmethod
    def from_settings(cls, settings: Any) -> AdCopyRefreshExecutor:
        """Create executor with fresh LLM client and a lazy prompt repo (own session per call)."""
        from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
            _LazyPromptRepo,
        )
        from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
        return cls(llm=AnthropicClient(api_key=settings.LLM_API_KEY), prompt_repo=_LazyPromptRepo(settings))  # type: ignore[arg-type]

    async def execute(
        self,
        rec: Recommendation,
        mutations: GoogleAdsMutationsPort,
        refresh_token: str,
        customer_id: str,
    ) -> dict[str, Any]:
        ev = rec.evidence
        ad_group_id = int(ev.get("ad_group_id", rec.target.get("ad_group_id", 0)))
        final_url = ev.get("final_url", "")
        lowest_ctr_ad_id: int | None = ev.get("lowest_ctr_ad_id")

        use_case = AdCopyRefreshUseCase(llm=self._llm, prompt_repo=self._prompt_repo)
        proposals = await use_case.execute(rec)

        created_ad_ids: list[int] = []
        for proposal in proposals:
            ad_id = await mutations.create_rsa(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                headlines=proposal.headlines,
                descriptions=proposal.descriptions,
                final_url=final_url or proposal.final_url,
            )
            created_ad_ids.append(ad_id)

        for ad_id in created_ad_ids:
            await mutations.enable_ad(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                ad_id=ad_id,
            )

        paused_ad_id: int | None = None
        if lowest_ctr_ad_id:
            paused_ad_id = int(lowest_ctr_ad_id)
            await mutations.pause_ad(
                refresh_token=refresh_token,
                customer_id=customer_id,
                ad_group_id=ad_group_id,
                ad_id=paused_ad_id,
            )

        logger.info(
            "ad_copy_refresh.executed",
            account_id=str(rec.account_id),
            ad_group_id=ad_group_id,
            created_ad_ids=created_ad_ids,
            paused_ad_id=paused_ad_id,
        )

        return {
            "ad_group_id": ad_group_id,
            "created_ad_ids": created_ad_ids,
            "paused_ad_id": paused_ad_id,
            "action": "ad_copy_refreshed",
        }
