"""Tests for PMax API endpoints — Phase 6 Task 6.3."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adcopilot.application.ports.google_ads import MerchantCenterLink
from adcopilot.config import get_settings
from adcopilot.interfaces.api.auth_middleware import get_current_user
from adcopilot.interfaces.api.pmax import _NO_MC_INSTRUCTIONS, router

# ---------------------------------------------------------------------------
# Shared helpers
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
    mock_settings.LLM_API_KEY = "test-llm-key"
    app.dependency_overrides[get_settings] = lambda: mock_settings

    return app


def _mock_account(write_enabled: bool = True) -> MagicMock:
    account = MagicMock()
    account.id = "acc-uuid-1"
    account.user_id = "user-1"
    account.customer_id = "1234567890"
    account.write_enabled = write_enabled
    return account


def _mock_creds() -> MagicMock:
    creds = MagicMock()
    creds.refresh_token = "rt-test"
    return creds


def _mock_user(plan: str = "growth") -> MagicMock:
    from adcopilot.domain.entities import PlanTier

    user = MagicMock()
    user.plan = PlanTier(plan)
    return user


def _infra_patches(account=None, creds=None):
    """Return a context-manager stack that mocks DB + Google Ads infra."""
    if account is None:
        account = _mock_account()
    if creds is None:
        creds = _mock_creds()

    mock_session = AsyncMock()
    mock_session.begin = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    import sqlalchemy.ext.asyncio as sqla_async

    import adcopilot.infrastructure.db.repositories.google_ads_account_repository as acct_mod
    import adcopilot.infrastructure.db.repositories.oauth_credentials_repository as oauth_mod

    mock_account_repo = AsyncMock()
    mock_account_repo.get = AsyncMock(return_value=account)
    mock_oauth_repo = AsyncMock()
    mock_oauth_repo.get = AsyncMock(return_value=creds)

    return (
        patch.object(sqla_async, "create_async_engine", return_value=mock_engine),
        patch.object(sqla_async, "AsyncSession", return_value=mock_session),
        patch.object(acct_mod, "SqlGoogleAdsAccountRepository", return_value=mock_account_repo),
        patch.object(oauth_mod, "SqlOAuthCredentialsRepository", return_value=mock_oauth_repo),
    )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_eligibility_with_mc_link():
    app = _make_app()
    mc_link = MerchantCenterLink(merchant_id=42, account_name="Test Sklep", status="ENABLED")

    import adcopilot.infrastructure.google_ads.queries_adapter as qa_mod

    mock_adapter = AsyncMock()
    mock_adapter.get_merchant_center_link = AsyncMock(return_value=mc_link)

    p1, p2, p3, p4 = _infra_patches()
    with p1, p2, p3, p4, patch.object(qa_mod, "GoogleAdsQueriesAdapter", return_value=mock_adapter):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/user-1/pmax/eligibility?account_id=acc-uuid-1")

    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is True
    assert data["merchant_center"]["merchant_id"] == 42
    assert data["merchant_center"]["account_name"] == "Test Sklep"
    assert data["instructions_pl"] is None


def test_eligibility_without_mc_link():
    app = _make_app()

    import adcopilot.infrastructure.google_ads.queries_adapter as qa_mod

    mock_adapter = AsyncMock()
    mock_adapter.get_merchant_center_link = AsyncMock(return_value=None)

    p1, p2, p3, p4 = _infra_patches()
    with p1, p2, p3, p4, patch.object(qa_mod, "GoogleAdsQueriesAdapter", return_value=mock_adapter):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/api/user-1/pmax/eligibility?account_id=acc-uuid-1")

    assert response.status_code == 200
    data = response.json()
    assert data["eligible"] is False
    assert data["merchant_center"] is None
    assert "Merchant Center" in data["instructions_pl"]


def test_eligibility_forbidden():
    app = _make_app(user_id="other-user")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/user-1/pmax/eligibility?account_id=acc-1")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Create PMax
# ---------------------------------------------------------------------------


def test_create_pmax_forbidden_write_disabled():
    app = _make_app()

    p1, p2, p3, p4 = _infra_patches(account=_mock_account(write_enabled=False))
    with p1, p2, p3, p4:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/user-1/pmax/create",
            json={
                "account_id": "acc-uuid-1",
                "monthly_budget_pln": 1500,
                "campaign_name": "Test",
                "final_url": "https://sklep.pl",
            },
        )

    assert response.status_code == 403
    assert "zapisu" in response.json()["detail"]


def test_create_pmax_forbidden_starter_plan():
    app = _make_app()

    import adcopilot.infrastructure.db.repositories.user_repository as user_mod

    mock_user_repo = AsyncMock()
    mock_user_repo.get = AsyncMock(return_value=_mock_user(plan="starter"))

    p1, p2, p3, p4 = _infra_patches()
    with p1, p2, p3, p4, patch.object(user_mod, "SqlUserRepository", return_value=mock_user_repo):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/user-1/pmax/create",
            json={
                "account_id": "acc-uuid-1",
                "monthly_budget_pln": 1500,
                "campaign_name": "Test",
                "final_url": "https://sklep.pl",
            },
        )

    assert response.status_code == 403
    assert "Growth" in response.json()["detail"]


def test_create_pmax_no_merchant_center():
    app = _make_app()

    import adcopilot.infrastructure.db.repositories.user_repository as user_mod
    import adcopilot.infrastructure.google_ads.queries_adapter as qa_mod

    mock_user_repo = AsyncMock()
    mock_user_repo.get = AsyncMock(return_value=_mock_user(plan="growth"))
    mock_adapter = AsyncMock()
    mock_adapter.get_merchant_center_link = AsyncMock(return_value=None)

    p1, p2, p3, p4 = _infra_patches()
    with (
        p1,
        p2,
        p3,
        p4,
        patch.object(user_mod, "SqlUserRepository", return_value=mock_user_repo),
        patch.object(qa_mod, "GoogleAdsQueriesAdapter", return_value=mock_adapter),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/user-1/pmax/create",
            json={
                "account_id": "acc-uuid-1",
                "monthly_budget_pln": 1500,
                "campaign_name": "Test",
                "final_url": "https://sklep.pl",
            },
        )

    assert response.status_code == 400
    assert "Merchant Center" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Enable PMax
# ---------------------------------------------------------------------------


def test_enable_pmax_forbidden_write_disabled():
    app = _make_app()

    p1, p2, p3, p4 = _infra_patches(account=_mock_account(write_enabled=False))
    with p1, p2, p3, p4:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/user-1/pmax/customers/123/campaigns/456/enable?account_id=acc-uuid-1"
        )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_pmax_status_forbidden():
    app = _make_app(user_id="other-user")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/user-1/pmax/status?account_id=acc-1")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_no_mc_instructions_in_polish():
    assert "Merchant Center" in _NO_MC_INSTRUCTIONS
    assert "merchants.google.com" in _NO_MC_INSTRUCTIONS
    assert "Google Ads" in _NO_MC_INSTRUCTIONS
