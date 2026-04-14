"""Tests for :mod:`adcopilot.security.cors`.

The CORS middleware is configured once at app startup, so these tests
target the pure helper that builds the allow-list — a regression here
would either leak localhost origins into prod or wildcard the allow-list.
Both would let any site in a user's browser hit our authenticated API.
"""

from __future__ import annotations

import pytest

from adcopilot.config import Settings
from adcopilot.security.cors import build_cors_allowed_origins


def _settings(env: str, app_url: str | None = None) -> Settings:
    return Settings(ENV=env, APP_URL=app_url)


# ---------------------------------------------------------------------------
# Production — strict: only APP_URL.
# ---------------------------------------------------------------------------


def test_production_only_allows_app_url() -> None:
    origins = build_cors_allowed_origins(_settings("production", "https://tryadept.com"))
    assert origins == ["https://tryadept.com"]


def test_production_rejects_missing_app_url() -> None:
    with pytest.raises(RuntimeError, match="APP_URL must be set in production"):
        build_cors_allowed_origins(_settings("production", None))


def test_production_rejects_wildcard_app_url() -> None:
    with pytest.raises(RuntimeError):
        build_cors_allowed_origins(_settings("production", "*"))


def test_production_does_not_include_localhost() -> None:
    origins = build_cors_allowed_origins(_settings("production", "https://tryadept.com"))
    for origin in origins:
        assert "localhost" not in origin
        assert "127.0.0.1" not in origin


def test_production_strips_trailing_slash() -> None:
    origins = build_cors_allowed_origins(_settings("production", "https://tryadept.com/"))
    assert origins == ["https://tryadept.com"]


# ---------------------------------------------------------------------------
# Non-production — localhost dev servers allowed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["dev", "local", "staging", "test"])
def test_non_production_allows_localhost(env: str) -> None:
    origins = build_cors_allowed_origins(_settings(env, None))
    assert "http://localhost:3000" in origins
    assert "http://localhost:5173" in origins


def test_non_production_appends_app_url_when_set() -> None:
    origins = build_cors_allowed_origins(_settings("staging", "https://staging.tryadept.com"))
    assert "https://staging.tryadept.com" in origins
    assert "http://localhost:3000" in origins


def test_non_production_ignores_wildcard_app_url() -> None:
    """Even in dev, an explicit "*" must be dropped — CORS with
    allow_credentials=True + "*" is invalid per the CORS spec."""
    origins = build_cors_allowed_origins(_settings("dev", "*"))
    assert "*" not in origins


# ---------------------------------------------------------------------------
# No wildcard ever leaks into the allow-list.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", ["dev", "local", "staging", "test", "production"])
def test_no_wildcard_in_output(env: str) -> None:
    # production branch requires APP_URL — give it a safe value.
    app_url = "https://tryadept.com" if env == "production" else None
    origins = build_cors_allowed_origins(_settings(env, app_url))
    assert "*" not in origins
    assert all("*" not in o for o in origins)
