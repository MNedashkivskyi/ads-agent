"""Auth-gating + registration tests for the new Tier-1 endpoints.

Confirms the conversion-tracking setup/verify and campaign-enable endpoints are
registered and reject unauthenticated requests. Happy-path behaviour is covered
by the use-case unit tests (SetupConversionTrackingUseCase, etc.) and exercised
end-to-end in the DB-backed integration suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # The campaign-enable route lives behind the greenfield creation kill-switch
    # (T1.1). Enable it here so this fixture still exercises its auth gating;
    # the kill-switch-off behaviour is asserted separately below.
    monkeypatch.setenv("CAMPAIGN_CREATION_ENABLED", "true")
    from adcopilot.config import get_settings
    from adcopilot.main import create_app

    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_creation_disabled(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CAMPAIGN_CREATION_ENABLED", "false")
    from adcopilot.config import get_settings
    from adcopilot.main import create_app

    get_settings.cache_clear()
    app = create_app()
    get_settings.cache_clear()
    return TestClient(app, raise_server_exceptions=False)


def test_setup_tracking_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/conversion-tracking/setup",
        json={"category": "LEAD", "platform": "wordpress"},
    )
    assert resp.status_code == 401


def test_verify_tracking_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/conversion-tracking/verify",
        json={"conversion_action_id": 123},
    )
    assert resp.status_code == 401


def test_enable_campaign_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/launch/00000000-0000-0000-0000-000000000001/enable",
        json={"override_conversion_check": False},
    )
    assert resp.status_code == 401


def test_setup_tracking_route_is_registered(client: TestClient) -> None:
    # 401 (not 404) proves the route exists; auth middleware runs before the body.
    paths = {r.path for r in client.app.routes}  # type: ignore[attr-defined]
    assert "/api/conversion-tracking/setup" in paths
    assert "/api/conversion-tracking/verify" in paths
    # Launch route present only because this fixture enables creation.
    assert "/api/launch/{brief_id}/enable" in paths


def test_enable_campaign_404_when_creation_disabled(
    client_creation_disabled: TestClient,
) -> None:
    # With the kill-switch off (default), the launch router is not mounted, so
    # the creation endpoint 404s while core conversion-tracking routes remain.
    resp = client_creation_disabled.post(
        "/api/launch/00000000-0000-0000-0000-000000000001/enable",
        json={"override_conversion_check": False},
    )
    assert resp.status_code == 404
    paths = {r.path for r in client_creation_disabled.app.routes}  # type: ignore[attr-defined]
    assert "/api/launch/{brief_id}/enable" not in paths
    assert "/api/conversion-tracking/setup" in paths
