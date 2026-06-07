"""Expired tokens must yield a clean 401 'Token expired' (no error-log noise)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from adcopilot.main import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


def test_expired_token_returns_401_token_expired(client: TestClient) -> None:
    from jose import jwt as jose_jwt

    from adcopilot.config import get_settings

    token = jose_jwt.encode(
        {"sub": "user-123", "exp": int(time.time()) - 3600},
        get_settings().SECRET_KEY,
        algorithm="HS256",
    )
    resp = client.get(
        "/api/users/user-123/recommendations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"].lower()


def test_valid_token_still_authenticates(client: TestClient) -> None:
    # A non-expired HS256 token signed with SECRET_KEY still passes auth
    # (it then hits the ownership check → 403 for a different user is fine here;
    # the point is it is NOT rejected as expired/invalid at the auth layer).
    from jose import jwt as jose_jwt

    from adcopilot.config import get_settings

    token = jose_jwt.encode({"sub": "owner"}, get_settings().SECRET_KEY, algorithm="HS256")
    resp = client.get(
        "/api/users/owner/recommendations",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Not a 401 — auth succeeded (status depends on data, e.g. 200/500 on DB).
    assert resp.status_code != 401
