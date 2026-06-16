"""Unit tests for pivot analytics events (Phase 6 / T6.4)."""

from __future__ import annotations

from unittest.mock import patch

from adcopilot.observability import analytics


def test_emit_never_raises() -> None:
    # Even if the underlying logger blows up, emit() must swallow it.
    with patch.object(analytics._analytics, "info", side_effect=RuntimeError("boom")):
        analytics.emit("trial_started", user_id="u1")  # must not raise


def test_subscription_changed_flags_paid_conversion() -> None:
    captured: dict = {}

    def _capture(_msg: str, **props):  # noqa: ANN003
        captured.update(props)

    with patch.object(analytics._analytics, "info", side_effect=_capture):
        analytics.subscription_changed("u1", old_plan="starter", new_plan="professional", status="active")
    assert captured["event"] == "subscription_changed"
    assert captured["paid_conversion"] is True


def test_subscription_changed_not_paid_for_downgrade() -> None:
    captured: dict = {}

    def _capture(_msg: str, **props):  # noqa: ANN003
        captured.update(props)

    with patch.object(analytics._analytics, "info", side_effect=_capture):
        analytics.subscription_changed("u1", old_plan="business", new_plan="starter", status="canceled")
    assert captured["paid_conversion"] is False


def test_upgrade_prompted_carries_capability() -> None:
    captured: dict = {}

    def _capture(_msg: str, **props):  # noqa: ANN003
        captured.update(props)

    with patch.object(analytics._analytics, "info", side_effect=_capture):
        analytics.upgrade_prompted("u1", "starter", "audiences")
    assert captured["event"] == "upgrade_prompted"
    assert captured["capability"] == "audiences"
