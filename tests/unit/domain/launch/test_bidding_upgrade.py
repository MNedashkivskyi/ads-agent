"""Unit tests for CheckBiddingUpgradeUseCase."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.use_cases.check_bidding_upgrade import CheckBiddingUpgradeUseCase
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    RecommendationKind,
    RecommendationStatus,
)
from adcopilot.domain.snapshot import CampaignSnapshot


def _make_campaign(
    campaign_id: int = 1,
    status: str = "ENABLED",
    bidding_strategy: str = "MAXIMIZE_CLICKS",
    conversions: float = 0.0,
    cost_micros: int = 1_000_000,
    target_cpa_micros: int | None = None,
) -> CampaignSnapshot:
    return CampaignSnapshot(
        id="snap-1",  # type: ignore[arg-type]
        account_id=AccountId("acc-1"),
        snapshot_date=date.today(),
        campaign_id=campaign_id,
        name=f"Campaign {campaign_id}",
        status=status,
        channel_type="SEARCH",
        budget_micros=1_000_000,
        bidding_strategy=bidding_strategy,
        impressions=1000,
        clicks=50,
        cost_micros=cost_micros,
        conversions=conversions,
        conv_value=0.0,
        target_cpa_micros=target_cpa_micros,
    )


def _make_use_case(
    campaigns: list[CampaignSnapshot],
    pending_recs: list | None = None,
) -> tuple[CheckBiddingUpgradeUseCase, AsyncMock]:
    snap_repo = AsyncMock()
    snap_repo.get_latest_snapshot_date.return_value = date.today()
    snap_repo.get_campaigns_by_date.return_value = campaigns

    rec_repo = AsyncMock()
    rec_repo.list_active_dedup_keys.return_value = {
        (r.kind, r.target_hash) for r in (pending_recs or [])
    }
    rec_repo.save = AsyncMock()

    uc = CheckBiddingUpgradeUseCase(snapshot_repo=snap_repo, rec_repo=rec_repo)
    return uc, rec_repo


class TestNoSnapshotData:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_snapshot(self) -> None:
        snap_repo = AsyncMock()
        snap_repo.get_latest_snapshot_date.return_value = None
        rec_repo = AsyncMock()
        uc = CheckBiddingUpgradeUseCase(snap_repo, rec_repo)
        result = await uc.execute(AccountId("acc-1"))
        assert result == []
        rec_repo.save.assert_not_called()


class TestMaximizeClicksUpgrade:
    @pytest.mark.asyncio
    async def test_recommends_upgrade_at_30_conversions(self) -> None:
        campaign = _make_campaign(conversions=30.0, bidding_strategy="MAXIMIZE_CLICKS")
        uc, rec_repo = _make_use_case([campaign])
        recs = await uc.execute(AccountId("acc-1"))
        assert len(recs) == 1
        assert recs[0].payload["suggested_strategy"] == "MAXIMIZE_CONVERSIONS"
        assert recs[0].kind == RecommendationKind.ADJUST_BIDDING_STRATEGY
        rec_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_upgrade_below_threshold(self) -> None:
        campaign = _make_campaign(conversions=29.9, bidding_strategy="MAXIMIZE_CLICKS")
        uc, rec_repo = _make_use_case([campaign])
        recs = await uc.execute(AccountId("acc-1"))
        assert recs == []
        rec_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_paused_campaigns(self) -> None:
        campaign = _make_campaign(
            conversions=50.0, status="PAUSED", bidding_strategy="MAXIMIZE_CLICKS"
        )
        uc, rec_repo = _make_use_case([campaign])
        recs = await uc.execute(AccountId("acc-1"))
        assert recs == []


class TestMaximizeConversionsUpgrade:
    @pytest.mark.asyncio
    async def test_recommends_target_cpa_at_50_conversions(self) -> None:
        campaign = _make_campaign(
            conversions=50.0,
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            target_cpa_micros=None,
            cost_micros=50_000_000,
        )
        uc, rec_repo = _make_use_case([campaign])
        recs = await uc.execute(AccountId("acc-1"))
        assert len(recs) == 1
        assert recs[0].payload["suggested_strategy"] == "TARGET_CPA"

    @pytest.mark.asyncio
    async def test_no_upgrade_when_target_cpa_already_set(self) -> None:
        campaign = _make_campaign(
            conversions=50.0,
            bidding_strategy="MAXIMIZE_CONVERSIONS",
            target_cpa_micros=500_000,
        )
        uc, rec_repo = _make_use_case([campaign])
        recs = await uc.execute(AccountId("acc-1"))
        assert recs == []


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_skips_campaign_with_existing_recommendation(self) -> None:
        from adcopilot.domain.recommendation import (
            Recommendation,
            RecommendationId,
            RecommendationSeverity,
        )

        campaign = _make_campaign(
            campaign_id=42, conversions=35.0, bidding_strategy="MAXIMIZE_CLICKS"
        )
        existing_rec = Recommendation(
            id=RecommendationId("existing"),
            account_id=AccountId("acc-1"),
            kind=RecommendationKind.ADJUST_BIDDING_STRATEGY,
            severity=RecommendationSeverity.HIGH,
            status=RecommendationStatus.PENDING,
            target={"campaign_id": 42},
            payload={"campaign_id": 42, "suggested_strategy": "MAXIMIZE_CONVERSIONS"},
            estimated_monthly_savings_micros=0,
            evidence={},
            created_at=datetime.now(UTC),
        )
        uc, rec_repo = _make_use_case([campaign], pending_recs=[existing_rec])
        recs = await uc.execute(AccountId("acc-1"))
        assert recs == []
        rec_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_campaign_with_declined_recommendation(self) -> None:
        from adcopilot.domain.recommendation import (
            Recommendation,
            RecommendationId,
            RecommendationSeverity,
        )

        campaign = _make_campaign(
            campaign_id=7, conversions=35.0, bidding_strategy="MAXIMIZE_CLICKS"
        )
        declined_rec = Recommendation(
            id=RecommendationId("declined"),
            account_id=AccountId("acc-1"),
            kind=RecommendationKind.ADJUST_BIDDING_STRATEGY,
            severity=RecommendationSeverity.HIGH,
            status=RecommendationStatus.DECLINED,
            target={"campaign_id": 7},
            payload={"campaign_id": 7, "suggested_strategy": "MAXIMIZE_CONVERSIONS"},
            estimated_monthly_savings_micros=0,
            evidence={},
            created_at=datetime.now(UTC),
        )
        uc, rec_repo = _make_use_case([campaign], pending_recs=[declined_rec])
        recs = await uc.execute(AccountId("acc-1"))
        assert recs == []
        rec_repo.save.assert_not_called()
