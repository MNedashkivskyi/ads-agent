"""Unit tests for Sentry observability: PII scrubbing, context propagation, env mapping."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from adcopilot.observability import sentry as sentry_mod
from adcopilot.observability.sentry import (
    _before_send,
    _resolve_environment,
    _resolve_release,
    _scrub,
    _scrub_str,
    clear_context,
    set_account_context,
    set_user_context,
)

# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------


class TestScrubString:
    """_scrub_str should redact tokens, emails, and Google Ads customer IDs."""

    def test_redacts_refresh_token(self) -> None:
        assert "[REDACTED]" in _scrub_str("refresh=ya29.a0AfH6SMA-SomeLongOpaqueToken")
        assert "ya29" not in _scrub_str("refresh=ya29.a0AfH6SMA-SomeLongOpaqueToken")

    def test_redacts_1_slash_token(self) -> None:
        scrubbed = _scrub_str("token=1//0dXSomeRefreshTokenOpaque")
        assert "[REDACTED]" in scrubbed
        assert "0dXSome" not in scrubbed

    def test_redacts_email_addresses(self) -> None:
        scrubbed = _scrub_str("user alice@example.com logged in")
        assert "alice@example.com" not in scrubbed
        assert "[REDACTED]" in scrubbed

    def test_redacts_customers_prefix(self) -> None:
        scrubbed = _scrub_str("GET /v17/customers/1234567890/campaigns")
        assert "1234567890" not in scrubbed
        assert "[REDACTED]" in scrubbed

    def test_redacts_bare_10_digit_customer_id(self) -> None:
        scrubbed = _scrub_str("customer_id=1234567890 status=ok")
        assert "1234567890" not in scrubbed

    def test_leaves_safe_strings_alone(self) -> None:
        safe = "account loaded for snapshot on 2026-04-14"
        assert _scrub_str(safe) == safe


class TestScrubRecursive:
    """_scrub walks dicts/lists and redacts both key-triggered and value-triggered PII."""

    def test_redacts_by_key_name(self) -> None:
        out = _scrub(
            {
                "refresh_token": "anything-here",
                "password": "hunter2",
                "access_token": "x",
                "authorization": "Bearer whatever",
            }
        )
        assert out == {
            "refresh_token": "[REDACTED]",
            "password": "[REDACTED]",
            "access_token": "[REDACTED]",
            "authorization": "[REDACTED]",
        }

    def test_redacts_nested_values(self) -> None:
        out = _scrub(
            {
                "extra": {
                    "message": "failed for alice@example.com on customers/1234567890",
                    "safe": "hello",
                }
            }
        )
        assert "alice@example.com" not in out["extra"]["message"]
        assert "1234567890" not in out["extra"]["message"]
        assert out["extra"]["safe"] == "hello"

    def test_redacts_lists(self) -> None:
        out = _scrub(["ya29.tokenhere", "normal-value"])
        assert out[0] == "[REDACTED]"
        assert out[1] == "normal-value"

    def test_is_depth_capped(self) -> None:
        # Construct a pathological deeply-nested dict — should not stack overflow.
        obj: dict[str, Any] = {"k": "v"}
        for _ in range(20):
            obj = {"k": obj}
        # No exception == pass
        _scrub(obj)


class TestBeforeSend:
    """_before_send must scrub all payload locations and attach context tags."""

    def setup_method(self) -> None:
        clear_context()

    def test_scrubs_request_body_and_extras(self) -> None:
        event = {
            "request": {"data": {"refresh_token": "ya29.x", "email": "a@b.com"}},
            "extra": {"customer_id": "1234567890", "note": "ok"},
        }
        out = _before_send(event, {})
        assert out is not None
        assert out["request"]["data"]["refresh_token"] == "[REDACTED]"
        assert out["request"]["data"]["email"] == "[REDACTED]"
        assert out["extra"]["customer_id"] == "[REDACTED]"
        assert out["extra"]["note"] == "ok"

    def test_strips_user_email_and_ip(self) -> None:
        event = {"user": {"email": "a@b.com", "ip_address": "1.2.3.4", "id": "u-1"}}
        out = _before_send(event, {})
        assert out is not None
        assert "email" not in out["user"]
        assert "ip_address" not in out["user"]
        assert out["user"]["id"] == "u-1"

    def test_scrubs_exception_values(self) -> None:
        event = {
            "exception": {
                "values": [
                    {
                        "type": "GoogleAdsError",
                        "value": "Bad request for customers/1234567890",
                    }
                ]
            }
        }
        out = _before_send(event, {})
        assert out is not None
        assert "1234567890" not in out["exception"]["values"][0]["value"]

    def test_attaches_user_id_tag_from_contextvar(self) -> None:
        set_user_context("user-abc")
        try:
            out = _before_send({}, {})
        finally:
            clear_context()
        assert out is not None
        assert out["tags"]["user_id"] == "user-abc"
        assert out["user"]["id"] == "user-abc"

    def test_attaches_account_id_tag_from_contextvar(self) -> None:
        set_account_context("acct-xyz")
        try:
            out = _before_send({}, {})
        finally:
            clear_context()
        assert out is not None
        assert out["tags"]["account_id"] == "acct-xyz"

    def test_scrubs_message_field(self) -> None:
        event = {"message": "Snapshot failed for customers/9999999999 — ya29.abc"}
        out = _before_send(event, {})
        assert out is not None
        assert "9999999999" not in out["message"]
        assert "ya29.abc" not in out["message"]


# ---------------------------------------------------------------------------
# Environment name mapping
# ---------------------------------------------------------------------------


class TestResolveEnvironment:
    @pytest.mark.parametrize(
        "app_env,expected",
        [
            ("production", "production"),
            ("PRODUCTION", "production"),
            ("staging", "staging"),
            ("stage", "staging"),
            ("local", "local"),
            ("dev", "local"),
            ("test", "local"),
            ("ci", "local"),
            ("", "local"),
        ],
    )
    def test_folds_unknown_envs_to_local(self, app_env: str, expected: str) -> None:
        assert _resolve_environment(app_env) == expected


# ---------------------------------------------------------------------------
# Release resolution
# ---------------------------------------------------------------------------


class TestResolveRelease:
    def test_prefers_sentry_release_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_RELEASE", "v1.2.3")
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "should-be-ignored")
        assert _resolve_release() == "v1.2.3"

    def test_falls_back_to_railway_sha(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTRY_RELEASE", raising=False)
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abcdef1")
        assert _resolve_release() == "abcdef1"

    def test_falls_back_to_git_sha_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTRY_RELEASE", raising=False)
        monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
        monkeypatch.setenv("GIT_SHA", "deadbee")
        assert _resolve_release() == "deadbee"

    def test_falls_back_to_git_cli(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTRY_RELEASE", raising=False)
        monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
        monkeypatch.delenv("GIT_SHA", raising=False)
        # _resolve_release uses subprocess.check_output — mock it.
        with patch("adcopilot.observability.sentry.subprocess.check_output") as check_output:
            check_output.return_value = "cafef00\n"
            assert _resolve_release() == "cafef00"


# ---------------------------------------------------------------------------
# init_sentry idempotency + no-op when DSN missing
# ---------------------------------------------------------------------------


class TestInitSentry:
    def setup_method(self) -> None:
        sentry_mod._initialised = False

    def teardown_method(self) -> None:
        sentry_mod._initialised = False

    def test_returns_false_when_dsn_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        from adcopilot.config import get_settings

        get_settings.cache_clear()
        assert sentry_mod.init_sentry(component="test") is False

    def test_calls_sentry_sdk_init_with_dsn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "https://public@example.ingest.sentry.io/123")
        monkeypatch.setenv("ENV", "staging")
        from adcopilot.config import get_settings

        get_settings.cache_clear()
        fake_init = MagicMock()
        with patch("sentry_sdk.init", fake_init), patch("sentry_sdk.set_tag"):
            result = sentry_mod.init_sentry(component="api")

        assert result is True
        fake_init.assert_called_once()
        kwargs = fake_init.call_args.kwargs
        assert kwargs["dsn"] == "https://public@example.ingest.sentry.io/123"
        assert kwargs["environment"] == "staging"
        assert kwargs["send_default_pii"] is False
        assert kwargs["before_send"] is sentry_mod._before_send

    def test_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "https://public@example.ingest.sentry.io/123")
        from adcopilot.config import get_settings

        get_settings.cache_clear()
        fake_init = MagicMock()
        with patch("sentry_sdk.init", fake_init), patch("sentry_sdk.set_tag"):
            assert sentry_mod.init_sentry(component="api") is True
            assert sentry_mod.init_sentry(component="api") is True
        assert fake_init.call_count == 1
