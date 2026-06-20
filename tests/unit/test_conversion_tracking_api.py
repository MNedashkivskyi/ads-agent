"""Unit tests for conversion tracking API endpoints (Task 1.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adcopilot.domain.conversion_audit import ConversionActionHealth, ConversionAuditResult
from adcopilot.domain.entities import AccountId


def _make_audit_result(
    overall: ConversionActionHealth = ConversionActionHealth.HEALTHY,
) -> ConversionAuditResult:
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


# ---------------------------------------------------------------------------
# Premium per-action plan + container endpoints
# ---------------------------------------------------------------------------


def test_get_plan_requires_auth(test_client: TestClient) -> None:
    resp = test_client.get("/api/user-123/conversion-tracking/plan")
    assert resp.status_code == 401


def test_get_plan_returns_items(test_client: TestClient) -> None:
    from adcopilot.application.use_cases.build_conversion_plan import build_conversion_plan
    from adcopilot.domain.conversion_tracking.setup import ConversionActionTagInfo

    actions = [
        ConversionActionTagInfo(
            conversion_action_id=1,
            name="Zakup",
            category="PURCHASE",
            conversion_id="AW-123456789",
            conversion_label="lbl1",
        ),
        ConversionActionTagInfo(
            conversion_action_id=2,
            name="Telefon",
            category="PHONE_CALL_LEAD",
            conversion_id="AW-123456789",
            conversion_label="lbl2",
        ),
    ]
    plan = build_conversion_plan(actions, "woocommerce", [])

    async def _fake_gather(user_id, settings):  # noqa: ANN001
        return "woocommerce", plan, "123-456", "refresh-token"

    with patch(
        "adcopilot.interfaces.api.conversion_tracking._gather_premium_plan",
        new=_fake_gather,
    ):
        resp = test_client.get(
            "/api/user-123/conversion-tracking/plan", headers=_auth_headers()
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "woocommerce"
    assert [i["category"] for i in body["items"]] == ["PURCHASE", "PHONE_CALL_LEAD"]
    assert body["items"][0]["trigger_kind"] == "page_url_contains"
    assert body["items"][1]["trigger_kind"] == "tel_click"


def test_post_container_builds_from_confirmed_plan(test_client: TestClient) -> None:
    payload = {
        "platform": "woocommerce",
        "items": [
            {
                "conversion_action_id": 1,
                "name": "Zakup",
                "category": "PURCHASE",
                "conversion_id": "AW-123456789",
                "conversion_label": "lbl1",
                "trigger_kind": "page_url_contains",
                "needs_user_input": False,
                "trigger_hint": "order-received",
                "value": 50.0,
                "currency": "PLN",
            }
        ],
    }
    resp = test_client.post(
        "/api/user-123/conversion-tracking/gtm-container",
        json=payload,
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "woocommerce"
    tags = body["container"]["containerVersion"]["tag"]
    assert len(tags) == 1
    params = {p["key"]: p.get("value") for p in tags[0]["parameter"]}
    assert params["conversionId"] == "123456789"  # AW- stripped
    assert params["conversionValue"] == "50.0"


def test_post_container_requires_auth(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/user-123/conversion-tracking/gtm-container", json={"items": []}
    )
    assert resp.status_code == 401
