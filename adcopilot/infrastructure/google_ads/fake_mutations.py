"""Fake GoogleAdsMutationsPort for unit tests."""

from __future__ import annotations


class FakeGoogleAdsMutations:
    """Records mutation calls without hitting the Google Ads API."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
