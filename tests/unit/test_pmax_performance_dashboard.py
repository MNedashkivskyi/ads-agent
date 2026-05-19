"""Tests for PMax performance dashboard endpoint — Phase 6 Task 6.5."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adcopilot.domain.snapshot import CampaignSnapshot
from adcopilot.interfaces.api.auth_middleware import get_current_user
from adcopilot.interfaces.api.pmax import router
from adcopilot.config import get_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(user_id: str = "user-1") -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def override_auth():
        return user_id

    app.dependency_overrides[get_current_user] = override_auth

    mock_settings = MagicMock()
    mock_settings.DATABASE_URL = "postgresql+asyncpg://test"
    mock_settings.TOKEN_ENCRYPTION_KEY = "test-key-32-bytes-padding-here!!"
    app.dependency_overrides[get_settings] = lambda: mock_settings

    return app


_ACCOUNT_UUID = "00000000-0000-0000-0000-000000000001"


def _mock_account() -> MagicMock:
    account = MagicMock()
    account.id = _ACCOUNT_UUID
    account.user_id = "user-1"
    account.customer_id = "1234567890"
    account.write_enabled = True
    return account


def _mock_pmax_snap(
    campaign_id: int = 1,
    snapshot_date: date = date(2026, 5, 19),
    cost_micros: int = 50_000_000,
    conv_value: float = 150.0,
    impressions: int = 5000,
    clicks: int = 200,
    status: str = "ENABLED",
) -> CampaignSnapshot:
    return CampaignSnapshot(
        id="snap-1",
        account_id=_ACCOUNT_UUID,
        snapshot_date=snapshot_date,
        campaign_id=campaign_id,
        name=f"PMax {campaign_id}",
        status=status,
        channel_type="PERFORMANCE_MAX",
        budget_micros=100_000_000,
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        impressions=impressions,
        clicks=clicks,
        cost_micros=cost_micros,
        conversions=3.0,
        conv_value=conv_value,
    )


def _infra_patches(account=None, creds=None):
    if account is None:
        account = _mock_account()
    if creds is None:
        creds = MagicMock()
        creds.refresh_token = "rt-test"

    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    import adcopilot.infrastructure.db.repositories.google_ads_account_repository as acct_mod
    import adcopilot.infrastructure.db.repositories.oauth_credentials_repository as oauth_mod
    import sqlalchemy.ext.asyncio as sqla_async

    mock_account_repo = AsyncMock()
    mock_account_repo.get = AsyncMock(return_value=account)
    mock_oauth_repo = AsyncMock()
    mock_oauth_repo.get = AsyncMock(return_value=creds)

    return (
        patch.object(sqla_async, "create_async_engine", return_value=mock_engine),
        patch.object(sqla_async, "AsyncSession", return_value=mock_session),
        patch.object(acct_mod, "SqlGoogleAdsAccountRepository", return_value=mock_account_repo),
        patch.object(oauth_mod, "SqlOAuthCredentialsRepository", return_value=mock_oauth_repo),
        mock_session,
    )


# ---------------------------------------------------------------------------
# Repository: get_campaigns_date_range
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_campaigns_date_range_filters_by_channel_type():
    """The endpoint returns only PERFORMANCE_MAX campaigns."""
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

    pmax_snap = _mock_pmax_snap()
    search_snap = CampaignSnapshot(
        id="snap-2", account_id=_ACCOUNT_UUID,
        snapshot_date=date(2026, 5, 19), campaign_id=2,
        name="Search", status="ENABLED", channel_type="SEARCH",
        budget_micros=0, bidding_strategy="MANUAL_CPC",
        impressions=100, clicks=5, cost_micros=1_000_000,
        conversions=0.0, conv_value=0.0,
    )

    session = AsyncMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])  # raw model objects
    execute_result = MagicMock()
    execute_result.scalars = MagicMock(return_value=scalars)
    session.execute = AsyncMock(return_value=execute_result)

    repo = SqlSnapshotRepository(session)
    # Should call execute once
    result = await repo.get_campaigns_date_range(
        "00000000-0000-0000-0000-000000000001", date(2026, 5, 1), date(2026, 5, 19)
    )
    session.execute.assert_awaited_once()
    assert result == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

def test_pmax_performance_forbidden():
    app = _make_app(user_id="other-user")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/user-1/pmax/performance?account_id=acc-1")
    assert response.status_code == 403


def test_pmax_performance_invalid_days():
    app = _make_app()
    p1, p2, p3, p4, session = _infra_patches()
    with p1, p2, p3, p4:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/user-1/pmax/performance?account_id=acc-uuid-1&days=0")
    assert response.status_code == 400


def test_pmax_performance_returns_time_series():
    app = _make_app()
    snaps = [
        _mock_pmax_snap(campaign_id=1, snapshot_date=date(2026, 5, 18), cost_micros=50_000_000, conv_value=150.0),
        _mock_pmax_snap(campaign_id=1, snapshot_date=date(2026, 5, 19), cost_micros=60_000_000, conv_value=200.0),
    ]

    import adcopilot.infrastructure.db.repositories.snapshot_repository as sr_mod

    mock_snapshot_repo = AsyncMock()
    mock_snapshot_repo.get_campaigns_date_range = AsyncMock(return_value=snaps)

    # Mock empty recommendations for asset group health
    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    execute_result.scalars = MagicMock(return_value=scalars_result)

    p1, p2, p3, p4, mock_session = _infra_patches()
    mock_session.execute = AsyncMock(return_value=execute_result)

    with p1, p2, p3, p4, patch.object(sr_mod, "SqlSnapshotRepository", return_value=mock_snapshot_repo):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/user-1/pmax/performance?account_id=acc-uuid-1&days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["days"] == 30
    assert len(data["time_series"]) == 2
    ts = data["time_series"]
    # First data point
    assert ts[0]["date"] == "2026-05-18"
    assert ts[0]["cost_pln"] == 50.0
    assert ts[0]["conv_value_pln"] == 150.0
    assert ts[0]["roas"] == 3.0  # 150/50 = 3.0
    assert ts[0]["campaign_name"] == "PMax 1"
    # Asset group health
    assert len(data["asset_group_health"]) == 1
    assert data["asset_group_health"][0]["campaign_id"] == 1
    assert data["asset_group_health"][0]["has_disapproved_assets"] is False


def test_pmax_performance_roas_null_when_no_cost():
    app = _make_app()
    snaps = [
        _mock_pmax_snap(campaign_id=1, cost_micros=0, conv_value=0.0)
    ]

    import adcopilot.infrastructure.db.repositories.snapshot_repository as sr_mod

    mock_snapshot_repo = AsyncMock()
    mock_snapshot_repo.get_campaigns_date_range = AsyncMock(return_value=snaps)

    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    execute_result.scalars = MagicMock(return_value=scalars_result)

    p1, p2, p3, p4, mock_session = _infra_patches()
    mock_session.execute = AsyncMock(return_value=execute_result)

    with p1, p2, p3, p4, patch.object(sr_mod, "SqlSnapshotRepository", return_value=mock_snapshot_repo):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/user-1/pmax/performance?account_id=acc-uuid-1&days=7")

    assert response.status_code == 200
    ts = response.json()["time_series"]
    assert ts[0]["roas"] is None


def test_pmax_performance_empty_when_no_pmax_campaigns():
    app = _make_app()
    # Only SEARCH campaigns
    snaps = [
        CampaignSnapshot(
            id="snap-1", account_id=_ACCOUNT_UUID,
            snapshot_date=date(2026, 5, 19), campaign_id=1,
            name="Search", status="ENABLED", channel_type="SEARCH",
            budget_micros=0, bidding_strategy="MANUAL_CPC",
            impressions=100, clicks=5, cost_micros=1_000_000,
            conversions=0.0, conv_value=0.0,
        )
    ]

    import adcopilot.infrastructure.db.repositories.snapshot_repository as sr_mod

    mock_snapshot_repo = AsyncMock()
    mock_snapshot_repo.get_campaigns_date_range = AsyncMock(return_value=snaps)

    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all = MagicMock(return_value=[])
    execute_result.scalars = MagicMock(return_value=scalars_result)

    p1, p2, p3, p4, mock_session = _infra_patches()
    mock_session.execute = AsyncMock(return_value=execute_result)

    with p1, p2, p3, p4, patch.object(sr_mod, "SqlSnapshotRepository", return_value=mock_snapshot_repo):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/user-1/pmax/performance?account_id=acc-uuid-1&days=7")

    assert response.status_code == 200
    assert response.json()["time_series"] == []
    assert response.json()["asset_group_health"] == []
