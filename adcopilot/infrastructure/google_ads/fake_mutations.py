"""Fake GoogleAdsMutationsPort for unit tests."""

from __future__ import annotations


class FakeGoogleAdsMutations:
    """Records mutation calls without hitting the Google Ads API."""

    def __init__(self, missing_campaign_ids: set[int] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        # Campaign ids that should be reported as non-existent / removed.
        self._missing_campaign_ids: set[int] = missing_campaign_ids or set()

    async def campaign_exists(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> bool:
        self.calls.append({"method": "campaign_exists", "campaign_id": campaign_id})
        return campaign_id not in self._missing_campaign_ids

    async def pause_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "pause_keyword",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "criterion_id": criterion_id,
            }
        )

    async def pause_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "pause_ad",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "ad_id": ad_id,
            }
        )

    async def add_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "add_ad_group_negative_keyword",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )

    async def update_campaign_budget(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        new_budget_micros: int,
    ) -> None:
        self.calls.append(
            {
                "method": "update_campaign_budget",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "new_budget_micros": new_budget_micros,
            }
        )

    async def pause_campaign(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "pause_campaign",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
            }
        )

    async def enable_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "enable_keyword",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "criterion_id": criterion_id,
            }
        )

    async def enable_ad(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        ad_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "enable_ad",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "ad_id": ad_id,
            }
        )

    async def remove_ad_group_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "remove_ad_group_negative_keyword",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )

    async def change_keyword_match_type(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        criterion_id: int,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "change_keyword_match_type",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "criterion_id": criterion_id,
                "match_type": match_type,
            }
        )

    async def set_campaign_bidding_strategy(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bidding_strategy: str,
    ) -> None:
        self.calls.append(
            {
                "method": "set_campaign_bidding_strategy",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "bidding_strategy": bidding_strategy,
            }
        )

    async def create_campaign_sitelinks(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        sitelinks: list[dict[str, str]],
    ) -> list[str]:
        rns = [f"customers/{customer_id}/campaignAssets/{i}" for i in range(len(sitelinks))]
        self.calls.append(
            {
                "method": "create_campaign_sitelinks",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "sitelinks": sitelinks,
                "rns": rns,
            }
        )
        return rns

    async def create_campaign_callouts(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        callout_texts: list[str],
    ) -> list[str]:
        rns = [f"customers/{customer_id}/campaignAssets/{i}" for i in range(len(callout_texts))]
        self.calls.append(
            {
                "method": "create_campaign_callouts",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "callout_texts": callout_texts,
                "rns": rns,
            }
        )
        return rns

    async def create_campaign_structured_snippets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        header: str,
        values: list[str],
    ) -> list[str]:
        rns = [f"customers/{customer_id}/campaignAssets/0"]
        self.calls.append(
            {
                "method": "create_campaign_structured_snippets",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "header": header,
                "values": values,
                "rns": rns,
            }
        )
        return rns

    async def remove_campaign_assets(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_asset_resource_names: list[str],
    ) -> None:
        self.calls.append(
            {
                "method": "remove_campaign_assets",
                "customer_id": customer_id,
                "campaign_asset_resource_names": campaign_asset_resource_names,
            }
        )

    async def set_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        bid_modifier: float,
    ) -> None:
        self.calls.append(
            {
                "method": "set_device_bid_modifier",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "bid_modifier": bid_modifier,
            }
        )

    async def remove_device_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "remove_device_bid_modifier",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
            }
        )

    async def exclude_geo_location(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "exclude_geo_location",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "location_id": location_id,
            }
        )

    async def remove_geo_exclusion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        location_id: int,
    ) -> None:
        self.calls.append(
            {
                "method": "remove_geo_exclusion",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "location_id": location_id,
            }
        )

    async def set_ad_schedule_bid_modifier(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
        bid_modifier: float,
    ) -> None:
        self.calls.append(
            {
                "method": "set_ad_schedule_bid_modifier",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "hour_of_day": hour_of_day,
                "bid_modifier": bid_modifier,
            }
        )

    async def remove_ad_schedule_criterion(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        hour_of_day: int,
    ) -> None:
        self.calls.append(
            {
                "method": "remove_ad_schedule_criterion",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "hour_of_day": hour_of_day,
            }
        )

    async def set_target_cpa(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        target_cpa_micros: int,
    ) -> None:
        self.calls.append(
            {
                "method": "set_target_cpa",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "target_cpa_micros": target_cpa_micros,
            }
        )

    async def remove_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "remove_campaign_negative_keyword",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )

    async def add_campaign_negative_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        campaign_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "add_campaign_negative_keyword",
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )

    async def add_keyword(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> int:
        self.calls.append(
            {
                "method": "add_keyword",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )
        return 99999  # fake criterion_id

    async def pause_ad_group_keyword_by_text(
        self,
        refresh_token: str,
        customer_id: str,
        ad_group_id: int,
        keyword_text: str,
        match_type: str,
    ) -> None:
        self.calls.append(
            {
                "method": "pause_ad_group_keyword_by_text",
                "customer_id": customer_id,
                "ad_group_id": ad_group_id,
                "keyword_text": keyword_text,
                "match_type": match_type,
            }
        )
