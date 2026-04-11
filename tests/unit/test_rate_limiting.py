"""Unit tests for auth endpoint rate limiting.

Tests use a memory-backed Limiter (no Redis required) injected via
app.state.limiter so the middleware reads the test limiter at runtime.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from slowapi import Limiter

from adcopilot.rate_limit import _get_real_ip

# ---------------------------------------------------------------------------
# _get_real_ip() — IP extraction logic
# ---------------------------------------------------------------------------


def _req(headers: dict[str, str] | None = None, client_host: str = "1.2.3.4") -> MagicMock:
    request = MagicMock()
    request.headers = headers or {}
    if client_host:
        request.client = MagicMock()
        request.client.host = client_host
    else:
        request.client = None
    return request


def test_get_real_ip_uses_x_real_ip_header() -> None:
    req = _req({"X-Real-IP": "10.0.0.1"})
    assert _get_real_ip(req) == "10.0.0.1"


def test_get_real_ip_uses_first_xff_entry() -> None:
    req = _req({"X-Forwarded-For": "203.0.113.1, 10.0.0.1, 127.0.0.1"})
    assert _get_real_ip(req) == "203.0.113.1"


def test_get_real_ip_prefers_x_real_ip_over_xff() -> None:
    req = _req({"X-Real-IP": "10.0.0.5", "X-Forwarded-For": "203.0.113.1"})
    assert _get_real_ip(req) == "10.0.0.5"


def test_get_real_ip_falls_back_to_client_host() -> None:
    req = _req(client_host="192.168.1.99")
    assert _get_real_ip(req) == "192.168.1.99"


def test_get_real_ip_returns_unknown_when_no_client() -> None:
    req = _req(client_host="")
    req.client = None
    assert _get_real_ip(req) == "unknown"


def test_get_real_ip_strips_whitespace() -> None:
    req = _req({"X-Real-IP": "  10.0.0.2  "})
    assert _get_real_ip(req) == "10.0.0.2"


# ---------------------------------------------------------------------------
# Rate limiting integration — memory backend, no Redis required
# ---------------------------------------------------------------------------


@pytest.fixture()
def rate_limited_client() -> TestClient:
    """TestClient backed by a memory-storage limiter with tight limits."""
    from adcopilot.main import create_app

    app = create_app()
    # Replace the Redis-backed limiter with an in-memory one so the test
    # doesn't need a running Redis instance.
    app.state.limiter = Limiter(key_func=_get_real_ip, storage_uri="memory://")
    return TestClient(app, raise_server_exceptions=False)


def test_limiter_is_registered_on_app_state() -> None:
    """The FastAPI app must expose limiter on app.state."""
    from adcopilot.main import create_app

    app = create_app()
    assert hasattr(app.state, "limiter")
    assert isinstance(app.state.limiter, Limiter)


def test_login_returns_429_after_limit_exceeded(rate_limited_client: TestClient) -> None:
    """The 6th login attempt from the same IP within one minute must get 429."""
    # Apply a tighter 3/minute limit directly on the test limiter so the test
    # doesn't need to make 6 real DB calls.
    from slowapi import Limiter

    from adcopilot.main import create_app
    from adcopilot.rate_limit import _get_real_ip

    app = create_app()
    app.state.limiter = Limiter(
        key_func=_get_real_ip,
        storage_uri="memory://",
        default_limits=["3/minute"],
    )
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"email": "x@example.com", "password": "wrong"}
    responses = [
        client.post("/api/auth/login", json=payload) for _ in range(4)
    ]
    # The first 3 must NOT be 429; the 4th must be 429.
    for r in responses[:3]:
        assert r.status_code != 429, f"Unexpected 429 on attempt {responses.index(r) + 1}"
    assert responses[3].status_code == 429


def test_signup_returns_429_after_limit_exceeded() -> None:
    """The 4th signup attempt (with default_limits=3/minute) must get 429."""
    from slowapi import Limiter

    from adcopilot.main import create_app
    from adcopilot.rate_limit import _get_real_ip

    app = create_app()
    app.state.limiter = Limiter(
        key_func=_get_real_ip,
        storage_uri="memory://",
        default_limits=["3/minute"],
    )
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"email": "new@example.com", "password": "pass"}
    responses = [
        client.post("/api/auth/signup", json=payload) for _ in range(4)
    ]
    for r in responses[:3]:
        assert r.status_code != 429
    assert responses[3].status_code == 429


def test_rate_limit_response_has_retry_after_header() -> None:
    """429 responses must include Retry-After so clients can back off."""
    from slowapi import Limiter

    from adcopilot.main import create_app
    from adcopilot.rate_limit import _get_real_ip

    app = create_app()
    app.state.limiter = Limiter(
        key_func=_get_real_ip,
        storage_uri="memory://",
        default_limits=["1/minute"],
        headers_enabled=True,
    )
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"email": "x@example.com", "password": "wrong"}
    client.post("/api/auth/login", json=payload)   # allowed
    response = client.post("/api/auth/login", json=payload)  # blocked

    assert response.status_code == 429
    # slowapi sets Retry-After when headers_enabled=True
    assert "Retry-After" in response.headers or "retry-after" in response.headers


def test_different_ips_are_limited_independently() -> None:
    """Requests from different IPs must have independent counters."""
    from slowapi import Limiter

    from adcopilot.main import create_app
    from adcopilot.rate_limit import _get_real_ip

    app = create_app()
    app.state.limiter = Limiter(
        key_func=_get_real_ip,
        storage_uri="memory://",
        default_limits=["1/minute"],
    )
    client = TestClient(app, raise_server_exceptions=False)

    payload = {"email": "x@example.com", "password": "wrong"}
    # First IP exhausts its quota
    client.post("/api/auth/login", json=payload, headers={"X-Real-IP": "1.1.1.1"})
    blocked = client.post(
        "/api/auth/login", json=payload, headers={"X-Real-IP": "1.1.1.1"}
    )
    assert blocked.status_code == 429

    # Second IP must still get through
    allowed = client.post(
        "/api/auth/login", json=payload, headers={"X-Real-IP": "2.2.2.2"}
    )
    assert allowed.status_code != 429
