"""finalize_hook_set — assemble the RSA payload and tag every shipped asset.

Builds the validated RSA from the selected hooks, pins the strongest headline to
slot 1, and — critically — persists every shipped asset tagged by angle + surface.
That tagging is the hard gate for Phase 4 attribution: without it the creative
learning loop has nothing to learn from.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_hook_repository import CieHookRepository
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookStatus
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun, HookRunStatus
from adcopilot.domain.campaign_intelligence.creatives.hook_set import HookSet

logger = structlog.get_logger(__name__)


class FinalizeHookSetUseCase:
    def __init__(self, repo: CieHookRepository) -> None:
        self._repo = repo

    async def run(self, run: HookRun, *, customer_id: str = "") -> dict:
        if run.id is None:
            raise ValueError("run must be persisted before finalization")
        selected = await self._repo.list_candidates(
            run.id, statuses=[HookStatus.SELECTED.value, HookStatus.FINALIZED.value]
        )
        hook_set = HookSet(selected)
        hook_set.validate()  # ≥3 headlines, ≥2 descriptions or raises
        hook_set.pin_top_headline()
        payload = hook_set.to_rsa_payload()

        for c in selected:
            c.status = HookStatus.FINALIZED
            await self._repo.save_candidate(c)

        # Tag every shipped asset by angle + surface — the Phase 4 attribution gate.
        await self._repo.record_shipped_assets(
            account_id=run.account_id,
            customer_id=customer_id,
            campaign_id=run.campaign_id,
            vertical=run.vertical,
            language=run.language,
            assets=selected,
        )

        await self._repo.set_rsa_payload(run.id, payload)
        await self._repo.set_run_status(run.id, HookRunStatus.FINALIZED)
        run.status = HookRunStatus.FINALIZED
        run.rsa_payload = payload
        logger.info("cie.hooks.finalized", run_id=run.id, assets=len(selected))
        return payload
