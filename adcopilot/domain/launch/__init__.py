"""Domain objects for the campaign-launch / creation feature.

All types in this package are pure-Python dataclasses and enums with
zero imports from FastAPI, SQLAlchemy, or the Google Ads SDK.
"""

from adcopilot.domain.launch.entities import (
    AdGroupProposal,
    AdProposal,
    CampaignBrief,
    CampaignBriefId,
    CampaignProposal,
    CampaignProposalId,
    KeywordProposal,
    LaunchStatus,
    MatchType,
)

__all__ = [
    "AdGroupProposal",
    "AdProposal",
    "CampaignBrief",
    "CampaignBriefId",
    "CampaignProposal",
    "CampaignProposalId",
    "KeywordProposal",
    "LaunchStatus",
    "MatchType",
]
