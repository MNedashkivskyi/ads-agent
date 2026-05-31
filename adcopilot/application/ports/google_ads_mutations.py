"""GoogleAdsMutationsPort — write operations against the Google Ads API."""

from __future__ import annotations

from typing import Protocol


class GoogleAdsMutationsPort(Protocol):
    async def campaign_exists(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> bool:
        """Return True if the campaign exists and is not REMOVED."""
        ...

    async def pause_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None: ...

    async def pause_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None: ...

    async def add_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None: ...

    async def update_campaign_budget(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        new_budget_micros: int,
    ) -> None: ...

    # --- Undo counterparts ---

    async def enable_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None: ...

    async def enable_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None: ...

    async def remove_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None: ...

    async def change_keyword_match_type(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
        match_type: str,
    ) -> None: ...

    async def set_campaign_bidding_strategy(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bidding_strategy: str,
    ) -> None: ...

    async def create_campaign_sitelinks(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        sitelinks: list[dict[str, str]],
    ) -> list[str]:
        """Create sitelink assets and link to campaign. Return CampaignAsset resource names."""
        ...

    async def create_campaign_callouts(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        callout_texts: list[str],
    ) -> list[str]:
        """Create callout assets and link to campaign. Return CampaignAsset resource names."""
        ...

    async def create_campaign_structured_snippets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        header: str,
        values: list[str],
    ) -> list[str]:
        """Create structured snippet asset and link to campaign. Return CampaignAsset resource names."""
        ...

    async def remove_campaign_assets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_asset_resource_names: list[str],
    ) -> None:
        """Remove CampaignAsset links (undo for extension executors)."""
        ...

    async def set_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bid_modifier: float,
    ) -> None: ...

    async def remove_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> None: ...

    async def exclude_geo_location(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None: ...

    async def remove_geo_exclusion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None: ...

    async def set_ad_schedule_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
        bid_modifier: float,
    ) -> None: ...

    async def remove_ad_schedule_criterion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
    ) -> None: ...

    async def set_target_cpa(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        target_cpa_micros: int,
    ) -> None: ...

    async def remove_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None: ...

    async def add_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None: ...

    async def add_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> int:
        """Add a keyword to an ad group; returns the new criterion_id."""
        ...

    async def pause_ad_group_keyword_by_text(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None: ...

    async def get_ad_group_resource_name(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
    ) -> str:
        """Return the canonical resource name for an ad group."""
        ...

    async def create_rsa(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        headlines: list[str],
        descriptions: list[str],
        final_url: str,
        path1: str | None = None,
        path2: str | None = None,
    ) -> int:
        """Create a PAUSED Responsive Search Ad; return new ad_id."""
        ...
