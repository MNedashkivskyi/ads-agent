"""SQLAlchemy implementation of CampaignProposalRepo."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CalloutProposal,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    MatchType,
    SitelinkProposal,
    StructuredSnippetProposal,
)
from adcopilot.infrastructure.db.models import (
    LaunchAdGroupModel,
    LaunchAdModel,
    LaunchCalloutModel,
    LaunchKeywordModel,
    LaunchProposalModel,
    LaunchSitelinkModel,
    LaunchStructuredSnippetModel,
)

# ---------------------------------------------------------------------------
# Domain ↔ ORM conversion
# ---------------------------------------------------------------------------


def _model_to_domain(
    proposal: LaunchProposalModel,
    ad_groups: list[LaunchAdGroupModel],
    keywords_by_group: dict[uuid.UUID, list[LaunchKeywordModel]],
    ads_by_group: dict[uuid.UUID, list[LaunchAdModel]],
    sitelinks: list[LaunchSitelinkModel] | None = None,
    callouts: list[LaunchCalloutModel] | None = None,
    snippets: list[LaunchStructuredSnippetModel] | None = None,
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

    domain_sitelinks = [
        SitelinkProposal(
            link_text=sl.link_text,
            description1=sl.description1,
            description2=sl.description2,
            final_url=sl.final_url,
        )
        for sl in (sitelinks or [])
    ]
    domain_callouts = [CalloutProposal(text=co.text) for co in (callouts or [])]
    domain_snippets = [
        StructuredSnippetProposal(header=sn.header, values=list(sn.values))
        for sn in (snippets or [])
    ]

    # Reconstruct brand ad from JSONB if present
    brand_ad: AdProposal | None = None
    if proposal.brand_ad:
        ba = proposal.brand_ad
        brand_ad = AdProposal(
            headlines=list(ba.get("headlines", [])),
            descriptions=list(ba.get("descriptions", [])),
            final_url=ba.get("final_url", "https://example.com"),
            path_segments=(ba.get("path1", ""), ba.get("path2", "")),
        )

    brand_keywords: list[KeywordProposal] = []
    for kw_dict in (proposal.brand_keywords or []):
        brand_keywords.append(
            KeywordProposal(
                text=kw_dict["text"],
                match_type=MatchType(kw_dict["match_type"]),
                estimated_cpc_micros=kw_dict["estimated_cpc_micros"],
            )
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
        sitelinks=domain_sitelinks,
        callouts=domain_callouts,
        structured_snippets=domain_snippets,
        estimated_cpc_range=(
            proposal.estimated_cpc_min_micros,
            proposal.estimated_cpc_max_micros,
        ),
        generated_at=proposal.generated_at,
        brand_campaign_name=proposal.brand_campaign_name,
        brand_keywords=brand_keywords,
        brand_daily_budget_micros=proposal.brand_daily_budget_micros or 0,
        brand_ad=brand_ad,
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
        brand_ad_dict = None
        if proposal.brand_ad:
            ba = proposal.brand_ad
            brand_ad_dict = {
                "headlines": list(ba.headlines),
                "descriptions": list(ba.descriptions),
                "final_url": ba.final_url,
                "path1": ba.path_segments[0],
                "path2": ba.path_segments[1],
            }

        brand_kw_list = [
            {
                "text": kw.text,
                "match_type": kw.match_type.value,
                "estimated_cpc_micros": kw.estimated_cpc_micros,
            }
            for kw in (proposal.brand_keywords or [])
        ] or None

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
            brand_campaign_name=proposal.brand_campaign_name,
            brand_keywords=brand_kw_list,
            brand_daily_budget_micros=proposal.brand_daily_budget_micros,
            brand_ad=brand_ad_dict,
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

        # Insert extension children
        for sl in proposal.sitelinks:
            self._session.add(
                LaunchSitelinkModel(
                    id=uuid.uuid4(),
                    proposal_id=proposal_id,
                    link_text=sl.link_text,
                    description1=sl.description1,
                    description2=sl.description2,
                    final_url=sl.final_url,
                )
            )

        for co in proposal.callouts:
            self._session.add(
                LaunchCalloutModel(
                    id=uuid.uuid4(),
                    proposal_id=proposal_id,
                    text=co.text,
                )
            )

        for sn in proposal.structured_snippets:
            self._session.add(
                LaunchStructuredSnippetModel(
                    id=uuid.uuid4(),
                    proposal_id=proposal_id,
                    header=sn.header,
                    values=list(sn.values),
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

        # Extensions
        sl_result = await self._session.execute(
            select(LaunchSitelinkModel).where(LaunchSitelinkModel.proposal_id == proposal.id)
        )
        sitelinks = list(sl_result.scalars().all())

        co_result = await self._session.execute(
            select(LaunchCalloutModel).where(LaunchCalloutModel.proposal_id == proposal.id)
        )
        callouts = list(co_result.scalars().all())

        sn_result = await self._session.execute(
            select(LaunchStructuredSnippetModel).where(
                LaunchStructuredSnippetModel.proposal_id == proposal.id
            )
        )
        snippets = list(sn_result.scalars().all())

        return _model_to_domain(proposal, ad_groups, kws_by_group, ads_by_group, sitelinks, callouts, snippets)
