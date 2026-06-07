"""LAUNCH-001: the /debug router must not be mounted in production."""

from __future__ import annotations

from unittest.mock import patch


def _paths(app) -> list[str]:
    return [getattr(r, "path", "") for r in app.routes]


def test_debug_router_absent_in_production() -> None:
    from adcopilot.config import Settings
    from adcopilot.main import create_app

    prod = Settings(ENV="production", APP_URL="https://app.example.com")
    with patch("adcopilot.main.get_settings", return_value=prod):
        app = create_app()
    assert not any(p.startswith("/debug") for p in _paths(app))


def test_debug_router_present_in_dev() -> None:
    from adcopilot.main import create_app

    app = create_app()  # default ENV=dev
    assert any(p.startswith("/debug") for p in _paths(app))


def test_raw_token_endpoints_removed() -> None:
    from adcopilot.interfaces.api import debug

    # The attacker-supplied-token endpoints must be gone entirely.
    assert not hasattr(debug, "create_test_account")
    assert not hasattr(debug, "google_ads_test")
