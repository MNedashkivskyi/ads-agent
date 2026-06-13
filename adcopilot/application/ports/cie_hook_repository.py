"""CieHookRepository — persistence port for hook runs, candidates, shipped assets."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookCandidate
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun, HookRunStatus


class CieHookRepository(Protocol):
    async def create_run(self, run: HookRun) -> str: ...

    async def get_run(self, run_id: str) -> HookRun | None: ...

    async def get_latest_run_for_campaign(
        self, campaign_id: str, user_id: str
    ) -> HookRun | None: ...

    async def set_run_status(
        self, run_id: str, status: HookRunStatus, error: str | None = None
    ) -> None: ...

    async def set_rsa_payload(self, run_id: str, payload: dict) -> None: ...

    async def replace_candidates(
        self, run_id: str, campaign_id: str, candidates: list[HookCandidate]
    ) -> None: ...

    async def list_candidates(
        self, run_id: str, *, statuses: list[str] | None = None
    ) -> list[HookCandidate]: ...

    async def save_candidate(self, candidate: HookCandidate) -> None: ...

    async def record_shipped_assets(
        self,
        *,
        account_id: str,
        customer_id: str,
        campaign_id: str | None,
        vertical: str,
        language: str,
        assets: list[HookCandidate],
    ) -> None:
        """Persist each shipped asset tagged by angle + surface (Phase 4 gate)."""
        ...
