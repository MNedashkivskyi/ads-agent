"""ADW-005: billing checkout/portal endpoints require auth + ownership."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _jwt(user_id: str = "user-123") -> dict:
    from jose import jwt

    from adcopilot.config import get_settings

    token = jwt.encode({"sub": user_id}, get_settings().SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    from adcopilot.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_checkout_requires_auth(client: TestClient) -> None:
    resp = client.post(
        "/api/billing/user-123/checkout",
        json={"plan": "starter", "success_url": "https://x", "cancel_url": "https://y"},
    )
    assert resp.status_code == 401


def test_checkout_denies_wrong_user(client: TestClient) -> None:
    resp = client.post(
        "/api/billing/user-123/checkout",
        json={"plan": "starter", "success_url": "https://x", "cancel_url": "https://y"},
        headers=_jwt("attacker"),
    )
    assert resp.status_code == 403


def test_portal_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/billing/user-123/portal")
    assert resp.status_code == 401


def test_portal_denies_wrong_user(client: TestClient) -> None:
    resp = client.post("/api/billing/user-123/portal", headers=_jwt("attacker"))
    assert resp.status_code == 403
