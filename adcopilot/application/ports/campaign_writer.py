"""CampaignWriterPort — Protocol for creating Google Ads campaigns from proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from adcopilot.domain.launch.entities import AdGroupProposal, AdProposal, CampaignProposal, KeywordProposal


@dataclass(frozen=True)
class CreatedCampaignResources:
    """All resource names created during a single campaign-creation run.

    Kept together so the writer can roll back atomically if any step fails.
    """

    campaign_resource_name: str
    budget_resource_name: str
    ad_group_resource_names: list[str]
    keyword_resource_names: list[str]
    ad_resource_names: list[str]
    negative_resource_names: list[str]


class CampaignWriterPort(Protocol):
    """Write operations for creating a full Google Ads campaign structure."""

    async def create_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        proposal: CampaignProposal,
    ) -> tuple[str, str]:
        """Create a campaign + shared budget; return (campaign_resource_name, budget_resource_name).

        The campaign is always created in PAUSED state.
        """
        ...

    async def create_ad_groups(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        ad_group_proposals: list[AdGroupProposal],
    ) -> list[str]:
        """Create ad groups under *campaign_resource_name*; return resource_names."""
        ...

    async def create_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        keyword_proposals: list[KeywordProposal],
    ) -> list[str]:
        """Create keywords under *ad_group_resource_name*; return resource_names."""
        ...

    async def create_ads(
        self,
        customer_id: str,
        refresh_token: str,
        ad_group_resource_name: str,
        ad_proposals: list[AdProposal],
    ) -> list[str]:
        """Create RSA ads under *ad_group_resource_name*; return resource_names."""
        ...

    async def create_negative_keywords(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
        negatives: list[str],
    ) -> list[str]:
        """Create campaign-level negative keywords; return resource_names."""
        ...

    async def enable_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        campaign_resource_name: str,
    ) -> None:
        """Transition a PAUSED campaign to ENABLED.

        Called only after explicit second user confirmation.
        """
        ...

    async def delete_draft_campaign(
        self,
        customer_id: str,
        refresh_token: str,
        resources: CreatedCampaignResources,
    ) -> None:
        """Delete all resources created so far; used for rollback on errors.

        Partial campaigns must never be left in the customer's account.
        """
        ...
