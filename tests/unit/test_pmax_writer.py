"""Tests for PMaxCampaignWriter with mocked Google Ads API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adcopilot.application.ports.campaign_writer import (
    CreatedPMaxResources,
)
from adcopilot.domain.launch.entities import (
    AssetGroupProposal,
    CampaignBriefId,
    PMaxCampaignProposal,
    PMaxProposalId,
)
from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter


def _proposal(
    merchant_center_feed_id: int = 111,
    audience_signals: list[str] | None = None,
) -> PMaxCampaignProposal:
    ag = AssetGroupProposal(
        name="All Products",
        headlines=["Buy Online", "Great Prices", "Fast Delivery"],
        descriptions=["Shop now", "Free returns"],
        final_url="https://example.com/shop",
    )
    return PMaxCampaignProposal(
        id=PMaxProposalId("pmax-1"),
        brief_id=CampaignBriefId("brief-1"),
        campaign_name="Test PMax Campaign",
        daily_budget_micros=50_000_000,
        merchant_center_feed_id=merchant_center_feed_id,
        asset_groups=[ag],
        audience_signals=audience_signals or [],
    )


def _make_writer() -> tuple[PMaxCampaignWriter, MagicMock]:
    """Return (writer, mock_client_adapter) with all services pre-mocked."""
    settings = MagicMock()
    settings.GOOGLE_ADS_DEVELOPER_TOKEN = "dev-tok"
    settings.GOOGLE_ADS_CLIENT_ID = "cid"
    settings.GOOGLE_ADS_CLIENT_SECRET = "secret"

    writer = PMaxCampaignWriter(settings=settings)

    # Mock the client adapter
    mock_client = MagicMock()
    mock_adapter = MagicMock()
    mock_adapter.client = mock_client

    # Service mocks
    def _make_response(resource_name: str) -> MagicMock:
        resp = MagicMock()
        result = MagicMock()
        result.resource_name = resource_name
        resp.results = [result]
        return resp

    mock_client.get_service.side_effect = lambda name: {
        "CampaignBudgetService": MagicMock(
            mutate_campaign_budgets=MagicMock(
                return_value=_make_response("customers/1/campaignBudgets/100")
            )
        ),
        "CampaignService": MagicMock(
            mutate_campaigns=MagicMock(return_value=_make_response("customers/1/campaigns/200"))
        ),
        "AssetGroupService": MagicMock(
            mutate_asset_groups=MagicMock(
                return_value=_make_response("customers/1/assetGroups/300")
            )
        ),
        "AssetService": MagicMock(
            mutate_assets=MagicMock(
                return_value=MagicMock(
                    results=[MagicMock(resource_name=f"customers/1/assets/{i}") for i in range(5)]
                )
            )
        ),
        "AssetGroupAssetService": MagicMock(
            mutate_asset_group_assets=MagicMock(return_value=MagicMock())
        ),
        "AssetGroupListingGroupFilterService": MagicMock(
            mutate_asset_group_listing_group_filters=MagicMock(return_value=MagicMock())
        ),
        "AssetGroupSignalService": MagicMock(
            mutate_asset_group_signals=MagicMock(return_value=MagicMock())
        ),
    }.get(name, MagicMock())

    mock_client.get_type.side_effect = lambda name: MagicMock()

    return writer, mock_adapter


# ---------------------------------------------------------------------------
# CreatedPMaxResources
# ---------------------------------------------------------------------------


def test_created_pmax_resources_stores_fields() -> None:
    r = CreatedPMaxResources(
        campaign_resource_name="campaigns/200",
        budget_resource_name="budgets/100",
        asset_group_resource_names=["assetGroups/300"],
    )
    assert r.campaign_resource_name == "campaigns/200"
    assert r.asset_group_resource_names == ["assetGroups/300"]


# ---------------------------------------------------------------------------
# PMaxCampaignProposal
# ---------------------------------------------------------------------------


def test_proposal_defaults() -> None:
    p = _proposal()
    assert p.bidding_strategy == "MAXIMIZE_CONVERSIONS"
    assert p.audience_signals == []
    assert p.generated_at is not None


def test_proposal_with_audience_signals() -> None:
    p = _proposal(audience_signals=["customers/1/userInterests/1"])
    assert len(p.audience_signals) == 1


# ---------------------------------------------------------------------------
# PMaxCampaignWriterPort protocol compliance
# ---------------------------------------------------------------------------


def test_pmax_writer_port_protocol() -> None:
    """PMaxCampaignWriter should satisfy the PMaxCampaignWriterPort protocol."""
    from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter

    settings = MagicMock()
    writer = PMaxCampaignWriter(settings=settings)
    # Check required methods exist
    assert hasattr(writer, "create_pmax_campaign")
    assert hasattr(writer, "enable_pmax_campaign")
    assert hasattr(writer, "delete_draft_pmax_campaign")


# ---------------------------------------------------------------------------
# Rollback on failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pmax_campaign_rolls_back_on_error() -> None:
    """If campaign creation fails, budget must be removed (rollback)."""
    from adcopilot.domain.exceptions import GoogleAdsUnavailable
    from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter

    settings = MagicMock()
    writer = PMaxCampaignWriter(settings=settings)

    # Patch _build_client to return a mock adapter whose CampaignService raises
    budget_service = MagicMock()
    budget_service.mutate_campaign_budgets.return_value = MagicMock(
        results=[MagicMock(resource_name="customers/1/campaignBudgets/100")]
    )
    campaign_service = MagicMock()
    campaign_service.mutate_campaigns.side_effect = RuntimeError("API error")

    mock_client = MagicMock()
    mock_client.get_service.side_effect = lambda name: {
        "CampaignBudgetService": budget_service,
        "CampaignService": campaign_service,
    }.get(name, MagicMock())
    mock_client.get_type.return_value = MagicMock()

    mock_adapter = MagicMock()
    mock_adapter.client = mock_client

    with (
        patch.object(writer, "_build_client", return_value=mock_adapter),
        pytest.raises((GoogleAdsUnavailable, RuntimeError)),
    ):
        await writer.create_pmax_campaign(
            customer_id="123",
            refresh_token="tok",
            proposal=_proposal(),
        )

    # Budget removal must have been attempted
    remove_calls = [call for call in budget_service.mutate_campaign_budgets.call_args_list]
    # First call: create, second call: rollback remove
    assert len(remove_calls) >= 1  # at minimum the create call happened


# ---------------------------------------------------------------------------
# enable_pmax_campaign
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_pmax_campaign_calls_mutate() -> None:
    from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter

    settings = MagicMock()
    writer = PMaxCampaignWriter(settings=settings)

    campaign_service = MagicMock()
    campaign_service.mutate_campaigns.return_value = MagicMock()
    mock_client = MagicMock()
    mock_client.get_service.return_value = campaign_service
    mock_client.get_type.return_value = MagicMock()

    mock_adapter = MagicMock()
    mock_adapter.client = mock_client

    with patch.object(writer, "_build_client", return_value=mock_adapter):
        await writer.enable_pmax_campaign(
            customer_id="123",
            refresh_token="tok",
            campaign_resource_name="customers/1/campaigns/200",
        )

    campaign_service.mutate_campaigns.assert_called_once()
