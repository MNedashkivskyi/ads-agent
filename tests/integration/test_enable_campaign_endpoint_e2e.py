"""Endpoint-level tests for the campaign enable gate (B5).

Drives the real POST /api/launch/{brief_id}/enable handler: the conversion gate
branches and the Celery dispatch. DB-load boundaries (brief/account/creds repos)
and the Google Ads query adapter are faked; the task dispatch is mocked. (The
ORM uses Postgres-only types, so we fake the repo `.get` calls rather than seed
a DB; full DB coverage lives in the Postgres integration suite.)
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Spins up the app against sqlite+aiosqlite (handler engine only; DB-load faked).
# Marked integration so CI's "-m not integration" unit job deselects it.
pytestmark = pytest.mark.integration

_USER_ID = "11111111-1111-1111-1111-111111111111"
_BRIEF_ID = "22222222-2222-2222-2222-222222222222"

_BRIEF_GET = "adcopilot.infrastructure.db.repositories.launch_brief_repository.SqlCampaignBriefRepository.get"
_ACC_GET = "adcopilot.infrastructure.db.repositories.google_ads_account_repository.SqlGoogleAdsAccountRepository.get"
_CREDS_GET = "adcopilot.infrastructure.db.repositories.oauth_credentials_repository.SqlOAuthCredentialsRepository.get"
_QUERIES = "adcopilot.infrastructure.google_ads.queries_adapter.GoogleAdsQueriesAdapter.list_conversion_actions"
_TASK = "adcopilot.interfaces.worker.tasks.enable_campaign_task"


def _brief(*, primary_action="lead"):
    from adcopilot.domain.launch.entities import LaunchStatus

    return SimpleNamespace(
        user_id=_USER_ID,
        status=LaunchStatus.CREATED_PAUSED,
        account_id="acc-id",
        primary_action=primary_action,
        campaign_resource_name="customers/123/campaigns/456",
    )


def _account():
    return SimpleNamespace(id=str(uuid.uuid4()), customer_id="123-456-7890")


def _creds():
    return SimpleNamespace(refresh_token="rt")


def _macro_action():
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.snapshot import ConversionActionSnapshot, SnapshotId

    return ConversionActionSnapshot(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=AccountId("123"),
        snapshot_date=__import__("datetime").date(2026, 1, 1),
        conversion_action_id=7,
        name="Purchase",
        category="PURCHASE",
        counting_type="ONE_PER_CLICK",
        status="ENABLED",
        include_in_conversions_metric=True,
        all_conversions=3.0,
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
            "TOKEN_ENCRYPTION_KEY": "test-key-32-bytes-long-padding!!",
            "ENV": "test",
            # Drives the launch enable route, behind the creation kill-switch
            # (T1.1) — enable it so the launch router mounts.
            "CAMPAIGN_CREATION_ENABLED": "true",
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


def _base_patches():
    return (
        patch(_BRIEF_GET, new=AsyncMock(return_value=_brief())),
        patch(_ACC_GET, new=AsyncMock(return_value=_account())),
        patch(_CREDS_GET, new=AsyncMock(return_value=_creds())),
    )


def test_blocks_conversion_goal_without_tracking(client):
    b, a, c = _base_patches()
    with b, a, c, \
        patch(_QUERIES, new=AsyncMock(return_value=[])), \
        patch(_TASK) as task:
        resp = client.post(
            f"/api/launch/{_BRIEF_ID}/enable",
            json={"override_conversion_check": False},
        )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["error"] == "no_conversion_tracking"
    task.delay.assert_not_called()


def test_override_bypasses_gate_and_enables(client):
    b, a, c = _base_patches()
    with b, a, c, \
        patch(_QUERIES, new=AsyncMock(return_value=[])) as q, \
        patch(_TASK) as task:
        resp = client.post(
            f"/api/launch/{_BRIEF_ID}/enable",
            json={"override_conversion_check": True},
        )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "enabling"
    q.assert_not_called()  # override skips the tracking check
    task.delay.assert_called_once_with(_BRIEF_ID, skip_conversion_check=True)


def test_enables_when_tracking_present(client):
    b, a, c = _base_patches()
    with b, a, c, \
        patch(_QUERIES, new=AsyncMock(return_value=[_macro_action()])), \
        patch(_TASK) as task:
        resp = client.post(
            f"/api/launch/{_BRIEF_ID}/enable",
            json={"override_conversion_check": False},
        )
    assert resp.status_code == 202, resp.text
    task.delay.assert_called_once_with(_BRIEF_ID, skip_conversion_check=False)


def test_non_conversion_goal_enables_without_tracking(client):
    with patch(_BRIEF_GET, new=AsyncMock(return_value=_brief(primary_action="visit"))), \
        patch(_ACC_GET, new=AsyncMock(return_value=_account())), \
        patch(_CREDS_GET, new=AsyncMock(return_value=_creds())), \
        patch(_QUERIES, new=AsyncMock(return_value=[])) as q, \
        patch(_TASK) as task:
        resp = client.post(
            f"/api/launch/{_BRIEF_ID}/enable",
            json={"override_conversion_check": False},
        )
    assert resp.status_code == 202, resp.text
    q.assert_not_called()  # "visit" goal doesn't require tracking
    task.delay.assert_called_once()
