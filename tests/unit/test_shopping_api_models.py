"""SH3: shopping health API response-model contract."""

from __future__ import annotations

from adcopilot.interfaces.api.shopping import (
    AssetGroupHealth,
    PMaxCampaignHealth,
    ShoppingHealthResponse,
)


def test_shopping_health_response_shape() -> None:
    resp = ShoppingHealthResponse(
        snapshot_date="2026-06-03",
        campaigns=[
            PMaxCampaignHealth(
                campaign_id=99,
                name="PMax 1",
                channel_type="PERFORMANCE_MAX",
                cost_pln=120.0,
                conv_value=300.0,
                roas=2.5,
                asset_groups=[
                    AssetGroupHealth(
                        asset_group_id=11,
                        name="AG",
                        ad_strength="POOR",
                        primary_status="ELIGIBLE",
                        cost_pln=60.0,
                        conv_value=150.0,
                    )
                ],
                listing_group_count=1,
                catch_all_only=True,
            )
        ],
    )
    dumped = resp.model_dump()
    assert dumped["campaigns"][0]["roas"] == 2.5
    assert dumped["campaigns"][0]["catch_all_only"] is True
    assert dumped["campaigns"][0]["asset_groups"][0]["ad_strength"] == "POOR"


def test_roas_nullable_when_no_spend() -> None:
    c = PMaxCampaignHealth(
        campaign_id=1, name="x", channel_type="SHOPPING", cost_pln=0.0, conv_value=0.0,
        roas=None, asset_groups=[], listing_group_count=0, catch_all_only=False,
    )
    assert c.roas is None
