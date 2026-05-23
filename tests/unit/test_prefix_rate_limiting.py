"""Tests for :mod:`adcopilot.security.rate_limiting`.

The middleware is exercised directly against a minimal Starlette app — no
FastAPI routes, no Redis — so the tests stay hermetic and fast.  A full
integration test against the real FastAPI app is covered in
``test_security_integration.py``.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from adcopilot.security.rate_limiting import (
    PathPrefixRateLimitMiddleware,
    PrefixRateLimitConfig,
    build_default_prefix_rate_limits,
)


def _echo(_request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _app(configs: list[PrefixRateLimitConfig]) -> TestClient:
    routes = [
        Route("/api/ping", _echo),
        Route("/oauth/google/start", _echo),
        Route("/webhooks/stripe", _echo),
        Route("/health", _echo),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(
        PathPrefixRateLimitMiddleware,
        storage_uri="memory://",
        configs=configs,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_default_config_covers_all_required_prefixes() -> None:
    """The spec requires /oauth/, /api/, /webhooks/."""
    prefixes = {c.prefix for c in build_default_prefix_rate_limits()}
    assert {"/oauth/", "/api/", "/webhooks/"} <= prefixes


def test_default_config_limit_values() -> None:
    """Exact limits required by the security-hardening brief."""
    by_prefix = {c.prefix: c.limit for c in build_default_prefix_rate_limits()}
    assert by_prefix["/oauth/"] == "10/minute"
    assert by_prefix["/api/"] == "60/minute"
    assert by_prefix["/webhooks/"] == "100/minute"


def test_api_prefix_returns_429_after_limit() -> None:
    """61st /api/* request within a window from the same IP returns 429."""
    client = _app([PrefixRateLimitConfig("/api/", "2/minute")])

    assert client.get("/api/ping", headers={"X-Real-IP": "1.1.1.1"}).status_code == 200
    assert client.get("/api/ping", headers={"X-Real-IP": "1.1.1.1"}).status_code == 200
    blocked = client.get("/api/ping", headers={"X-Real-IP": "1.1.1.1"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_oauth_prefix_limited_independently_from_api() -> None:
    """Exhausting /api/ must not affect /oauth/."""
    client = _app(
        [
            PrefixRateLimitConfig("/api/", "1/minute"),
            PrefixRateLimitConfig("/oauth/", "1/minute"),
        ]
    )
    hdr = {"X-Real-IP": "2.2.2.2"}
    client.get("/api/ping", headers=hdr)
    assert client.get("/api/ping", headers=hdr).status_code == 429
    # /oauth still has its budget.
    assert client.get("/oauth/google/start", headers=hdr).status_code == 200


def test_webhook_prefix_has_its_own_counter() -> None:
    client = _app([PrefixRateLimitConfig("/webhooks/", "1/minute")])
    hdr = {"X-Real-IP": "3.3.3.3"}
    assert client.get("/webhooks/stripe", headers=hdr).status_code == 200
    assert client.get("/webhooks/stripe", headers=hdr).status_code == 429


def test_unrelated_path_is_not_limited() -> None:
    """/health must not be touched by prefix limiter."""
    client = _app([PrefixRateLimitConfig("/api/", "1/minute")])
    hdr = {"X-Real-IP": "5.5.5.5"}
    for _ in range(5):
        resp = client.get("/health", headers=hdr)
        assert resp.status_code == 200


def test_different_ips_counted_separately() -> None:
    client = _app([PrefixRateLimitConfig("/api/", "1/minute")])
    assert client.get("/api/ping", headers={"X-Real-IP": "9.9.9.1"}).status_code == 200
    assert client.get("/api/ping", headers={"X-Real-IP": "9.9.9.1"}).status_code == 429
    # Other IP unaffected.
    assert client.get("/api/ping", headers={"X-Real-IP": "9.9.9.2"}).status_code == 200


@pytest.mark.parametrize(
    "path,expected_match",
    [
        ("/api/foo", "/api/"),
        ("/oauth/google/start", "/oauth/"),
        ("/webhooks/stripe", "/webhooks/"),
        ("/health", None),
    ],
)
def test_longest_prefix_match(path: str, expected_match: str | None) -> None:
    mw = PathPrefixRateLimitMiddleware(
        app=lambda *a, **kw: None,  # type: ignore[arg-type,return-value]
        storage_uri="memory://",
    )
    result = mw._match(path)
    if expected_match is None:
        assert result is None
    else:
        assert result is not None
        assert result[0] == expected_match
