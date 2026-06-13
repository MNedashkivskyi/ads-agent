"""generate_hooks — allocate angles, generate hooks, policy-screen, persist."""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_hook_repository import CieHookRepository
from adcopilot.application.ports.hook_generator import HookGeneratorPort
from adcopilot.domain.campaign_intelligence.creatives import angle_selector, policy_screener
from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun, HookRunStatus
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)
from adcopilot.domain.exceptions import LLMError

logger = structlog.get_logger(__name__)

DEFAULT_TOTAL_SLOTS = 14  # ~2 hooks per angle across 7 angles
DEFAULT_SURFACES = [AdSurface.HEADLINE, AdSurface.DESCRIPTION]


class GenerateHooksUseCase:
    def __init__(self, generator: HookGeneratorPort, repo: CieHookRepository) -> None:
        self._generator = generator
        self._repo = repo

    async def run(
        self,
        run: HookRun,
        *,
        total_slots: int = DEFAULT_TOTAL_SLOTS,
        surfaces: list[AdSurface] | None = None,
        learned_performance: dict[str, DimensionPerformance] | None = None,
    ) -> HookRun:
        if run.id is None:
            raise ValueError("run must be persisted before generation")
        surfaces = surfaces or DEFAULT_SURFACES
        allocation = angle_selector.allocate(total_slots, learned_performance or {})
        logger.info("cie.hooks.generate", run_id=run.id, allocation=allocation)

        try:
            generated = await self._generator.generate(
                service=run.service,
                vertical=run.vertical,
                problems=run.problems,
                angle_allocation=allocation,
                surfaces=[s.value for s in surfaces],
                language=run.language,
            )
        except LLMError as exc:
            await self._repo.set_run_status(run.id, HookRunStatus.FAILED, str(exc))
            run.status = HookRunStatus.FAILED
            raise

        candidates: list[HookCandidate] = []
        for g in generated:
            try:
                angle = Angle(g.angle)
                candidate = HookCandidate(
                    text=g.text,
                    angle=angle,
                    surface=AdSurface(g.surface),
                    policy=policy_screener.screen(g.text, angle),
                )
            except ValueError:
                continue  # over-limit or invalid — drop
            candidates.append(candidate)

        await self._repo.replace_candidates(run.id, run.campaign_id, candidates)
        await self._repo.set_run_status(run.id, HookRunStatus.READY)
        run.status = HookRunStatus.READY
        logger.info("cie.hooks.generated", run_id=run.id, count=len(candidates))
        return run
