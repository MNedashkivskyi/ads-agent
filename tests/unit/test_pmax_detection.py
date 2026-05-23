"""Tests for PMax eligibility detection and domain entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.detect_pmax_eligibility import (
    DetectPMaxEligibilityUseCase,
    _is_ecommerce,
)
from adcopilot.domain.launch.entities import (
    AssetGroupProposal,
    CampaignBriefId,
    PMaxCampaignProposal,
    PMaxProposalId,
)

# ---------------------------------------------------------------------------
# _is_ecommerce() helper
# ---------------------------------------------------------------------------


def test_is_ecommerce_exact_match() -> None:
    assert _is_ecommerce("ecommerce") is True


def test_is_ecommerce_sklep() -> None:
    assert _is_ecommerce("sklep internetowy") is True


def test_is_ecommerce_partial() -> None:
    assert _is_ecommerce("e-commerce retail") is True


def test_is_ecommerce_non_ecommerce() -> None:
    assert _is_ecommerce("salon") is False
    assert _is_ecommerce("legal") is False
    assert _is_ecommerce("medical") is False
    assert _is_ecommerce("restaurant") is False


def test_is_ecommerce_generic() -> None:
    assert _is_ecommerce("generic") is False


# ---------------------------------------------------------------------------
# DetectPMaxEligibilityUseCase
# ---------------------------------------------------------------------------


def _make_uc(feeds: list[dict]) -> DetectPMaxEligibilityUseCase:
    provider = MagicMock()
    provider.query_merchant_center_feed = AsyncMock(return_value=feeds)
    return DetectPMaxEligibilityUseCase(feed_provider=provider)


@pytest.mark.asyncio
async def test_ecommerce_with_enabled_feed_is_eligible() -> None:
    feeds = [{"feed_id": 111, "name": "My Shop", "status": "ENABLED"}]
    uc = _make_uc(feeds)
    result = await uc.run(vertical="ecommerce", refresh_token="tok", customer_id="123")
    assert result.eligible is True
    assert len(result.feeds) == 1
    assert result.feeds[0]["feed_id"] == 111


@pytest.mark.asyncio
async def test_ecommerce_without_feed_not_eligible() -> None:
    uc = _make_uc([])
    result = await uc.run(vertical="ecommerce", refresh_token="tok", customer_id="123")
    assert result.eligible is False
    assert result.feeds == []


@pytest.mark.asyncio
async def test_ecommerce_with_pending_feed_not_eligible() -> None:
    """Only ENABLED feeds count — PENDING/CANCELLED do not trigger PMax offer."""
    feeds = [{"feed_id": 222, "name": "Pending Shop", "status": "PENDING"}]
    uc = _make_uc(feeds)
    result = await uc.run(vertical="ecommerce", refresh_token="tok", customer_id="123")
    assert result.eligible is False


@pytest.mark.asyncio
async def test_non_ecommerce_vertical_not_eligible_without_api_call() -> None:
    provider = MagicMock()
    provider.query_merchant_center_feed = AsyncMock()
    uc = DetectPMaxEligibilityUseCase(feed_provider=provider)
    result = await uc.run(vertical="salon", refresh_token="tok", customer_id="123")
    assert result.eligible is False
    provider.query_merchant_center_feed.assert_not_called()


@pytest.mark.asyncio
async def test_api_error_gracefully_returns_not_eligible() -> None:
    provider = MagicMock()
    provider.query_merchant_center_feed = AsyncMock(side_effect=RuntimeError("API down"))
    uc = DetectPMaxEligibilityUseCase(feed_provider=provider)
    # Should NOT raise — graceful degradation
    result = await uc.run(vertical="ecommerce", refresh_token="tok", customer_id="123")
    assert result.eligible is False


# ---------------------------------------------------------------------------
# PMaxCampaignProposal entity
# ---------------------------------------------------------------------------


def test_pmax_proposal_creation() -> None:
    asset_group = AssetGroupProposal(
        name="All Products",
        headlines=["Buy Online", "Great Prices", "Fast Delivery"],
        descriptions=["Shop our full catalog", "Free returns on all orders"],
        final_url="https://example.com/shop",
    )
    proposal = PMaxCampaignProposal(
        id=PMaxProposalId("pmax-1"),
        brief_id=CampaignBriefId("brief-1"),
        campaign_name="PMax – My Shop",
        daily_budget_micros=50_000_000,
        merchant_center_feed_id=111,
        asset_groups=[asset_group],
    )
    assert proposal.merchant_center_feed_id == 111
    assert len(proposal.asset_groups) == 1
    assert proposal.bidding_strategy == "MAXIMIZE_CONVERSIONS"
    assert proposal.audience_signals == []
    assert proposal.generated_at is not None


def test_asset_group_images_placeholder_defaults_to_empty() -> None:
    ag = AssetGroupProposal(
        name="Group A",
        headlines=["H1", "H2", "H3"],
        descriptions=["D1", "D2"],
        final_url="https://example.com",
    )
    assert ag.images_placeholder == []
