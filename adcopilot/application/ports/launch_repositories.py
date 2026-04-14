"""Repository Protocols for the campaign-launch bounded context.

These are *interfaces* only — no implementation details.  Concrete
implementations live in ``adcopilot.infrastructure.db.repositories``.
"""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.entities import UserId
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    LaunchStatus,
)


class CampaignBriefRepo(Protocol):
    """Persistence contract for ``CampaignBrief`` aggregates."""

    async def get(self, brief_id: CampaignBriefId) -> CampaignBrief | None:
        """Return the brief with the given id, or ``None`` if not found."""
        ...

    async def list_for_user(self, user_id: UserId) -> list[CampaignBrief]:
        """Return all briefs belonging to *user_id*, newest first."""
        ...

    async def save(self, brief: CampaignBrief) -> CampaignBrief:
        """Persist *brief* (insert or update) and return the saved entity."""
        ...

    async def update_status(
        self,
        brief_id: CampaignBriefId,
        status: LaunchStatus,
    ) -> None:
        """Transition the status of an existing brief in-place."""
        ...


class CampaignProposalRepo(Protocol):
    """Persistence contract for ``CampaignProposal`` value objects."""

    async def get(self, proposal_id: CampaignProposalId) -> CampaignProposal | None:
        """Return the proposal with the given id, or ``None`` if not found."""
        ...

    async def get_by_brief(self, brief_id: CampaignBriefId) -> CampaignProposal | None:
        """Return the most recent proposal for *brief_id*, or ``None``."""
        ...

    async def save(self, proposal: CampaignProposal) -> CampaignProposal:
        """Persist *proposal* (insert or update) and return the saved entity."""
        ...
