"""select_hooks — judge candidates, score, pick top-K per surface with diversity."""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_hook_repository import CieHookRepository
from adcopilot.application.ports.hook_generator import GeneratedHook, HookJudgePort
from adcopilot.domain.campaign_intelligence.creatives import hook_scorer, hook_selection
from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import (
    HookCandidate,
    HookStatus,
)
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun

logger = structlog.get_logger(__name__)

# Google Ads RSA maxima — headlines up to 15, descriptions up to 4.
DEFAULT_TOP_K = {AdSurface.HEADLINE: 8, AdSurface.DESCRIPTION: 4}


class SelectHooksUseCase:
    def __init__(self, judge: HookJudgePort, repo: CieHookRepository) -> None:
        self._judge = judge
        self._repo = repo

    async def run(
        self,
        run: HookRun,
        *,
        top_k_per_surface: dict[AdSurface, int] | None = None,
        learned_weights: dict[str, float] | None = None,
    ) -> list[HookCandidate]:
        if run.id is None:
            raise ValueError("run must be persisted before selection")
        top_k = top_k_per_surface or DEFAULT_TOP_K
        candidates = await self._repo.list_candidates(
            run.id, statuses=[HookStatus.GENERATED.value, HookStatus.SELECTED.value]
        )
        if not candidates:
            return []

        judge_results = await self._judge.judge(
            [GeneratedHook(c.text, c.angle.value, c.surface.value) for c in candidates],
            service=run.service,
            vertical=run.vertical,
            language=run.language,
        )
        by_text = {r.text: r for r in judge_results}
        for c in candidates:
            jr = by_text.get(c.text)
            hook_scorer.score_candidate(
                c, judge=jr.overall if jr else 0.0, learned_weights=learned_weights
            )

        selected = hook_selection.select_hooks(candidates, top_k)
        selected_ids = {id(c) for c in selected}
        for c in candidates:
            c.status = HookStatus.SELECTED if id(c) in selected_ids else HookStatus.GENERATED
            await self._repo.save_candidate(c)

        logger.info("cie.hooks.selected", run_id=run.id, selected=len(selected))
        return selected
