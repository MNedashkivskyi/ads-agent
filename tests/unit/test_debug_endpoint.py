"""Smoke tests for the /debug/sentry endpoint and FastAPI Sentry middleware."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adcopilot.interfaces.api.debug import SentryDebugError, router
from adcopilot.observability.fastapi_middleware import (
    SentryContextMiddleware,
    _extract_user_id_from_jwt,
)


def _app_with_debug_router() -> FastAPI:
    """Build a minimal FastAPI app with only the debug router + sentry middleware."""
    app = FastAPI()
    app.add_middleware(SentryContextMiddleware)
    app.include_router(router)
    return app


def test_debug_endpoint_raises_sentry_debug_error() -> None:
    """The endpoint must raise — TestClient surfaces it unless raise_server_exceptions=False."""
    app = _app_with_debug_router()
    with (
        pytest.raises(SentryDebugError, match="Deliberate test error"),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        client.get("/debug/sentry")


def test_debug_endpoint_returns_500_without_raise() -> None:
    """Verifies the endpoint propagates to a 500 when the TestClient swallows exceptions."""
    app = _app_with_debug_router()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.get("/debug/sentry")
    assert resp.status_code == 500


def test_debug_endpoint_captures_user_id_tag_from_auth_header() -> None:
    """When a Bearer JWT is present, the middleware tags the Sentry scope with user_id.

    We patch ``set_user_context`` to capture the call rather than inspecting
    Sentry state directly — the unit under test is the middleware, not the SDK.
    """
    app = _app_with_debug_router()

    # Build a JWT with a known sub.  We deliberately use get_unverified_claims,
    # so any valid JWT shape works.
    from jose import jwt as jose_jwt

    token = jose_jwt.encode({"sub": "user-42"}, "unused-secret", algorithm="HS256")

    with (
        patch("adcopilot.observability.fastapi_middleware.set_user_context") as mock_set,
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        client.get("/debug/sentry", headers={"Authorization": f"Bearer {token}"})
    mock_set.assert_called_with("user-42")


# ---------------------------------------------------------------------------
# _extract_user_id_from_jwt helper
# ---------------------------------------------------------------------------


class TestExtractUserIdFromJwt:
    def test_returns_sub_for_valid_jwt(self) -> None:
        from jose import jwt as jose_jwt

        token = jose_jwt.encode({"sub": "abc"}, "x", algorithm="HS256")
        assert _extract_user_id_from_jwt(f"Bearer {token}") == "abc"

    def test_returns_none_for_missing_header(self) -> None:
        assert _extract_user_id_from_jwt(None) is None

    def test_returns_none_for_non_bearer(self) -> None:
        assert _extract_user_id_from_jwt("Basic abcdef") is None

    def test_returns_none_for_malformed_jwt(self) -> None:
        assert _extract_user_id_from_jwt("Bearer not-a-jwt") is None

    def test_returns_none_for_empty_token(self) -> None:
        assert _extract_user_id_from_jwt("Bearer ") is None
