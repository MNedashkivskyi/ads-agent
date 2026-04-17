"""SQLAlchemy implementation of CampaignProposalRepo."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
)
from adcopilot.infrastructure.db.models import (
    LaunchAdGroupModel,
    LaunchAdModel,
    LaunchKeywordModel,
    LaunchProposalModel,
)

# ---------------------------------------------------------------------------
# Domain ↔ ORM conversion
# ---------------------------------------------------------------------------


def _model_to_domain(
    proposal: LaunchProposalModel,
    ad_groups: list[LaunchAdGroupModel],
    keywords_by_group: dict[uuid.UUID, list[LaunchKeywordModel]],
    ads_by_group: dict[uuid.UUID, list[LaunchAdModel]],
) -> CampaignProposal:
    domain_ad_groups: list[AdGroupProposal] = []

    for ag in sorted(ad_groups, key=lambda x: x.position):
        kw_models = keywords_by_group.get(ag.id, [])
        ad_models = ads_by_group.get(ag.id, [])

        domain_kws = [
            KeywordProposal(
                text=kw.text,
                match_type=MatchType(kw.match_type),
                estimated_cpc_micros=kw.estimated_cpc_micros,
            )
            for kw in kw_models
        ]

        domain_ads = [
            AdProposal(
                headlines=list(ad.headlines),
                descriptions=list(ad.descriptions),
                final_url=ad.final_url,
                path_segments=(ad.path1, ad.path2),
            )
            for ad in ad_models
        ]

        domain_ad_groups.append(
            AdGroupProposal(name=ag.name, keywords=domain_kws, ads=domain_ads)
        )

    return CampaignProposal(
        id=CampaignProposalId(str(proposal.id)),
        brief_id=CampaignBriefId(str(proposal.brief_id)),
        campaign_name=proposal.campaign_name,
        daily_budget_micros=proposal.daily_budget_micros,
        location_targeting=proposal.location_targeting,
        bidding_strategy=proposal.bidding_strategy,
        ad_groups=domain_ad_groups,
        negative_keywords=list(proposal.negative_keywords),
        estimated_cpc_range=(
            proposal.estimated_cpc_min_micros,
            proposal.estimated_cpc_max_micros,
        ),
        generated_at=proposal.generated_at,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class SqlCampaignProposalRepository:
    """Persists ``CampaignProposal`` aggregates across five related tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, proposal_id: CampaignProposalId) -> CampaignProposal | None:
        proposal = await self._session.get(LaunchProposalModel, uuid.UUID(proposal_id))
        if proposal is None:
            return None
        return await self._load_full(proposal)

    async def get_by_brief(self, brief_id: CampaignBriefId) -> CampaignProposal | None:
        result = await self._session.execute(
            select(LaunchProposalModel)
            .where(LaunchProposalModel.brief_id == uuid.UUID(brief_id))
            .order_by(LaunchProposalModel.created_at.desc())
            .limit(1)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return None
        return await self._load_full(proposal)

    async def save(self, proposal: CampaignProposal) -> CampaignProposal:
        """Upsert the proposal (insert or replace) and return the saved entity."""
        proposal_id = uuid.UUID(proposal.id)

        # Delete any pre-existing rows for this id (cascade removes children)
        existing = await self._session.get(LaunchProposalModel, proposal_id)
        if existing is not None:
            await self._session.delete(existing)
            await self._session.flush()

        # Insert proposal root
        pm = LaunchProposalModel(
            id=proposal_id,
            brief_id=uuid.UUID(proposal.brief_id),
            campaign_name=proposal.campaign_name,
            daily_budget_micros=proposal.daily_budget_micros,
            location_targeting=proposal.location_targeting,
            bidding_strategy=proposal.bidding_strategy,
            negative_keywords=list(proposal.negative_keywords),
            estimated_cpc_min_micros=proposal.estimated_cpc_range[0],
            estimated_cpc_max_micros=proposal.estimated_cpc_range[1],
            generated_at=proposal.generated_at,
        )
        self._session.add(pm)

        # Insert ad groups + children
        for position, ag in enumerate(proposal.ad_groups):
            ag_id = uuid.uuid4()
            ag_model = LaunchAdGroupModel(
                id=ag_id,
                proposal_id=proposal_id,
                name=ag.name,
                position=position,
            )
            self._session.add(ag_model)

            for kw in ag.keywords:
                self._session.add(
                    LaunchKeywordModel(
                        id=uuid.uuid4(),
                        ad_group_id=ag_id,
                        text=kw.text,
                        match_type=kw.match_type.value,
                        estimated_cpc_micros=kw.estimated_cpc_micros,
                    )
                )

            for ad in ag.ads:
                self._session.add(
                    LaunchAdModel(
                        id=uuid.uuid4(),
                        ad_group_id=ag_id,
                        headlines=list(ad.headlines),
                        descriptions=list(ad.descriptions),
                        final_url=ad.final_url,
                        path1=ad.path_segments[0],
                        path2=ad.path_segments[1],
                    )
                )

        await self._session.flush()
        return proposal

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_full(self, proposal: LaunchProposalModel) -> CampaignProposal:
        """Load all children for *proposal* and assemble the domain object."""
        # Ad groups
        ag_result = await self._session.execute(
            select(LaunchAdGroupModel)
            .where(LaunchAdGroupModel.proposal_id == proposal.id)
            .order_by(LaunchAdGroupModel.position)
        )
        ad_groups = list(ag_result.scalars().all())
        ag_ids = [ag.id for ag in ad_groups]

        # Keywords
        kw_result = await self._session.execute(
            select(LaunchKeywordModel).where(
                LaunchKeywordModel.ad_group_id.in_(ag_ids)
            )
        )
        kws = list(kw_result.scalars().all())
        kws_by_group: dict[uuid.UUID, list[LaunchKeywordModel]] = {}
        for kw in kws:
            kws_by_group.setdefault(kw.ad_group_id, []).append(kw)

        # Ads
        ad_result = await self._session.execute(
            select(LaunchAdModel).where(LaunchAdModel.ad_group_id.in_(ag_ids))
        )
        ads = list(ad_result.scalars().all())
        ads_by_group: dict[uuid.UUID, list[LaunchAdModel]] = {}
        for ad in ads:
            ads_by_group.setdefault(ad.ad_group_id, []).append(ad)

        return _model_to_domain(proposal, ad_groups, kws_by_group, ads_by_group)
