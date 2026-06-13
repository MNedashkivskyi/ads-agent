"""SQL implementation of CieSearchTermRepository."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.campaign_intelligence.keywords.search_term import (
    PROMOTE,
    SearchTermProposal,
)
from adcopilot.infrastructure.db.models import CieSearchTermProposalModel


def _proposal_to_domain(m: CieSearchTermProposalModel) -> SearchTermProposal:
    return SearchTermProposal(
        term=m.term,
        kind=m.kind,
        impressions=m.impressions,
        clicks=m.clicks,
        conversions=m.conversions,
        cost_micros=m.cost_micros,
        ctr=m.ctr,
        intent=m.intent,
    )


class SqlCieSearchTermRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        written = 0
        for p in proposals:
            stmt = (
                pg_insert(CieSearchTermProposalModel)
                .values(
                    account_id=uuid.UUID(account_id),
                    customer_id=customer_id,
                    campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
                    term=p.term,
                    kind=p.kind,
                    intent=p.intent,
                    vertical=vertical,
                    language=language,
                    impressions=p.impressions,
                    clicks=p.clicks,
                    conversions=p.conversions,
                    cost_micros=p.cost_micros,
                    ctr=p.ctr,
                )
                .on_conflict_do_nothing(constraint="uq_cie_search_term_proposal")
            )
            await self._session.execute(stmt)
            written += 1
        return written

    async def list_promotion_terms(
        self, account_id: str, *, status: str = "proposed", limit: int = 50
    ) -> list[str]:
        result = await self._session.execute(
            select(CieSearchTermProposalModel.term)
            .where(
                CieSearchTermProposalModel.account_id == uuid.UUID(account_id),
                CieSearchTermProposalModel.kind == PROMOTE,
                CieSearchTermProposalModel.status == status,
            )
            .order_by(CieSearchTermProposalModel.conversions.desc())
            .limit(limit)
        )
        return [row[0] for row in result.all()]

    async def list_proposals(
        self, account_id: str, *, kind: str | None = None, status: str = "proposed"
    ) -> list[SearchTermProposal]:
        query = select(CieSearchTermProposalModel).where(
            CieSearchTermProposalModel.account_id == uuid.UUID(account_id),
            CieSearchTermProposalModel.status == status,
        )
        if kind is not None:
            query = query.where(CieSearchTermProposalModel.kind == kind)
        query = query.order_by(CieSearchTermProposalModel.conversions.desc())
        result = await self._session.execute(query)
        return [_proposal_to_domain(m) for m in result.scalars().all()]

    async def set_proposal_status(
        self, account_id: str, term: str, kind: str, status: str
    ) -> bool:
        result = await self._session.execute(
            update(CieSearchTermProposalModel)
            .where(
                CieSearchTermProposalModel.account_id == uuid.UUID(account_id),
                CieSearchTermProposalModel.term == term,
                CieSearchTermProposalModel.kind == kind,
            )
            .values(status=status)
        )
        return (result.rowcount or 0) > 0
