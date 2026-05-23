"""Unit tests for conversion tracking API endpoints (Task 1.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adcopilot.domain.conversion_audit import ConversionActionHealth, ConversionAuditResult
from adcopilot.domain.entities import AccountId


def _make_audit_result(overall: ConversionActionHealth = ConversionActionHealth.HEALTHY) -> ConversionAuditResult:
    from adcopilot.domain.conversion_audit import ConversionActionStatus

    return ConversionAuditResult(
        account_id=AccountId("123-456"),
        action_statuses=[
            ConversionActionStatus(
                action_id=1,
                name="Purchase",
                status="ENABLED",
                all_conversions=5.0,
                health=ConversionActionHealth.HEALTHY,
            )
        ],
        diagnostic_message_pl="Śledzenie konwersji działa poprawnie.",
        overall_health=overall,
    )


@pytest.fixture
def test_client() -> TestClient:
    from adcopilot.main import create_app
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _auth_headers(user_id: str = "user-123") -> dict:
    """Generate a valid JWT for testing."""
    from jose import jwt

    from adcopilot.config import get_settings
    settings = get_settings()
    token = jwt.encode({"sub": user_id}, settings.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_audit_requires_auth(test_client: TestClient) -> None:
    resp = test_client.get("/api/user-123/conversion-tracking/audit")
    assert resp.status_code == 401


def test_audit_denies_wrong_user(test_client: TestClient) -> None:
    headers = _auth_headers("other-user")
    resp = test_client.get("/api/user-123/conversion-tracking/audit", headers=headers)
    assert resp.status_code == 403


@patch("adcopilot.interfaces.api.conversion_tracking._run_audit")
def test_audit_returns_json(mock_run: MagicMock, test_client: TestClient) -> None:
    mock_run.return_value = _make_audit_result()
    headers = _auth_headers("user-123")

    resp = test_client.get("/api/user-123/conversion-tracking/audit", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_health"] == "healthy"
    assert data["account_id"] == "123-456"
    assert len(data["action_statuses"]) == 1
    assert data["action_statuses"][0]["name"] == "Purchase"


@patch("adcopilot.interfaces.api.conversion_tracking._run_audit")
def test_revalidate_returns_json(mock_run: MagicMock, test_client: TestClient) -> None:
    mock_run.return_value = _make_audit_result(ConversionActionHealth.STALE)
    headers = _auth_headers("user-123")

    resp = test_client.post("/api/user-123/conversion-tracking/revalidate", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_health"] == "stale"


def test_revalidate_requires_auth(test_client: TestClient) -> None:
    resp = test_client.post("/api/user-123/conversion-tracking/revalidate")
    assert resp.status_code == 401
