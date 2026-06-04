"""Endpoint-level tests for conversion-tracking setup + verify.

Exercises the real FastAPI handlers end-to-end (routing → auth → handler → use
case → response mapping) with the DB-load boundary and Google Ads adapters
faked. The ORM uses Postgres-only types (UUID/JSONB) that don't round-trip on
SQLite, so we fake ``_resolve_account_and_creds`` rather than seed a real DB;
a throwaway SQLite engine satisfies the handler's ``create_async_engine`` call
without needing any tables. Full DB-backed coverage lives in the Postgres
integration suite.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

_USER_ID = "11111111-1111-1111-1111-111111111111"
_ENC_KEY = "test-key-32-bytes-long-padding!!"
_CT = "adcopilot.interfaces.api.conversion_tracking"
_QUERIES = "adcopilot.infrastructure.google_ads.queries_adapter.GoogleAdsQueriesAdapter"
_MUTATIONS = "adcopilot.infrastructure.google_ads.mutations_adapter.GoogleAdsMutationsAdapter"


def _fake_account_and_creds():
    from adcopilot.domain.entities import AccountId, GoogleAdsAccount, OAuthCredentials, UserId

    account = GoogleAdsAccount(
        id=AccountId(str(uuid.uuid4())),
        user_id=UserId(_USER_ID),
        customer_id="123-456-7890",
        descriptive_name="E2E",
        currency="PLN",
        timezone="Europe/Warsaw",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    creds = OAuthCredentials(
        account_id=account.id,
        refresh_token="refresh-xyz",
        access_token=None,
        expires_at=None,
    )
    return account, creds


def _conv_action(*, category="PURCHASE", status="ENABLED", include=True, all_conversions=0.0):
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.snapshot import ConversionActionSnapshot, SnapshotId

    return ConversionActionSnapshot(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=AccountId("123"),
        snapshot_date=datetime.now(tz=UTC).date(),
        conversion_action_id=7,
        name="x",
        category=category,
        counting_type="ONE_PER_CLICK",
        status=status,
        include_in_conversions_metric=include,
        all_conversions=all_conversions,
    )


@pytest.fixture()
def client(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'noop.db'}"
    with patch.dict(
        os.environ,
        {
            "DATABASE_URL": db_url,
            "REDIS_URL": "redis://localhost:6379/15",
            "LLM_API_KEY": "",
            "TOKEN_ENCRYPTION_KEY": _ENC_KEY,
            "ENV": "test",
        },
    ):
        from adcopilot.config import get_settings

        get_settings.cache_clear()
        try:
            from fastapi.testclient import TestClient

            from adcopilot.interfaces.api.auth_middleware import get_current_user
            from adcopilot.main import create_app

            app = create_app()
            app.dependency_overrides[get_current_user] = lambda: _USER_ID
            yield TestClient(app, raise_server_exceptions=False)
        finally:
            get_settings.cache_clear()


def test_setup_creates_action_when_none_exists(client):
    from adcopilot.domain.conversion_tracking.setup import ConversionActionTag

    tag = ConversionActionTag(
        conversion_action_id=999,
        conversion_id="AW-123456789",
        conversion_label="AbC",
        global_site_tag="<script>...</script>",
        event_snippet="<script>gtag('event','conversion',{'send_to':'AW-123456789/AbC'})</script>",
    )
    with (
        patch(f"{_CT}._resolve_account_and_creds", new=AsyncMock(return_value=_fake_account_and_creds())),
        patch(f"{_QUERIES}.list_conversion_actions", new=AsyncMock(return_value=[])),
        patch(f"{_MUTATIONS}.create_conversion_action", new=AsyncMock(return_value=999)),
        patch(f"{_MUTATIONS}.get_conversion_action_tag_snippets", new=AsyncMock(return_value=tag)),
    ):
        resp = client.post(
            "/api/conversion-tracking/setup",
            json={"category": "LEAD", "platform": "wordpress"},
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["already_configured"] is False
    assert data["conversion_action_id"] == 999
    assert data["tag"]["conversion_id"] == "AW-123456789"
    assert data["message_pl"]


def test_setup_noops_when_macro_exists(client):
    with (
        patch(f"{_CT}._resolve_account_and_creds", new=AsyncMock(return_value=_fake_account_and_creds())),
        patch(
            f"{_QUERIES}.list_conversion_actions",
            new=AsyncMock(return_value=[_conv_action(category="PURCHASE")]),
        ),
        patch(f"{_MUTATIONS}.create_conversion_action", new=AsyncMock()) as create,
    ):
        resp = client.post(
            "/api/conversion-tracking/setup",
            json={"category": "PURCHASE", "platform": "custom"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["already_configured"] is True
    create.assert_not_called()


def test_setup_invalid_category_returns_422(client):
    with (
        patch(f"{_CT}._resolve_account_and_creds", new=AsyncMock(return_value=_fake_account_and_creds())),
        patch(f"{_QUERIES}.list_conversion_actions", new=AsyncMock(return_value=[])),
    ):
        resp = client.post("/api/conversion-tracking/setup", json={"category": "PAGE_VIEW"})
    assert resp.status_code == 422


def test_verify_reports_firing(client):
    with (
        patch(f"{_CT}._resolve_account_and_creds", new=AsyncMock(return_value=_fake_account_and_creds())),
        patch(
            f"{_QUERIES}.list_conversion_actions",
            new=AsyncMock(return_value=[_conv_action(all_conversions=4.0)]),
        ),
    ):
        resp = client.post("/api/conversion-tracking/verify", json={"conversion_action_id": 7})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["found"] is True
    assert data["is_firing"] is True
    assert data["recent_conversions"] == 4.0


def test_verify_not_firing_when_no_conversions(client):
    with (
        patch(f"{_CT}._resolve_account_and_creds", new=AsyncMock(return_value=_fake_account_and_creds())),
        patch(
            f"{_QUERIES}.list_conversion_actions",
            new=AsyncMock(return_value=[_conv_action(all_conversions=0.0)]),
        ),
    ):
        resp = client.post("/api/conversion-tracking/verify", json={"conversion_action_id": 7})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_firing"] is False
