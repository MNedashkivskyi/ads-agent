"""CieSearchTermRepository — persist harvested promotions + negatives."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.campaign_intelligence.keywords.search_term import SearchTermProposal


class CieSearchTermRepository(Protocol):
    async def save_proposals(
        self,
        *,
        account_id: str,
        customer_id: str,
        campaign_id: str | None,
        vertical: str,
        language: str,
        proposals: list[SearchTermProposal],
    ) -> int:
        """Idempotently persist proposals, keyed by (account, term, kind)."""
        ...

    async def list_promotion_terms(
        self, account_id: str, *, status: str = "proposed", limit: int = 50
    ) -> list[str]:
        """Promotion terms for seeding the next generation run (Phase 5.3)."""
        ...

    async def list_proposals(
        self, account_id: str, *, kind: str | None = None, status: str = "proposed"
    ) -> list[SearchTermProposal]:
        """Proposals for surfacing to the user (one-click adoption)."""
        ...

    async def set_proposal_status(self, account_id: str, term: str, kind: str, status: str) -> bool:
        """Mark a proposal adopted/dismissed; returns True if a row was updated."""
        ...
