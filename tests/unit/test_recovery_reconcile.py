"""Unit tests for reconcile_realized_saving (Audit Funnel Phase 4 — pure)."""

from __future__ import annotations

from adcopilot.application.audit.recovery import reconcile_realized_saving

_M = 1_000_000


def test_full_credit_when_flagged_spend_eliminated() -> None:
    # Entity spend dropped to zero (the fix held) -> credit the full projection.
    assert (
        reconcile_realized_saving(
            projected_micros=200 * _M, baseline_cost_micros=300 * _M, post_cost_micros=0
        )
        == 200 * _M
    )


def test_scaled_credit_when_spend_partly_remains() -> None:
    # Half the flagged spend remained -> half the projected saving.
    assert (
        reconcile_realized_saving(
            projected_micros=200 * _M, baseline_cost_micros=300 * _M, post_cost_micros=150 * _M
        )
        == 100 * _M
    )


def test_zero_when_spend_did_not_drop() -> None:
    assert (
        reconcile_realized_saving(
            projected_micros=200 * _M, baseline_cost_micros=300 * _M, post_cost_micros=400 * _M
        )
        == 0
    )


def test_trusts_projection_when_no_baseline() -> None:
    assert (
        reconcile_realized_saving(
            projected_micros=200 * _M, baseline_cost_micros=0, post_cost_micros=0
        )
        == 200 * _M
    )


def test_zero_projection_is_zero() -> None:
    assert (
        reconcile_realized_saving(
            projected_micros=0, baseline_cost_micros=300 * _M, post_cost_micros=0
        )
        == 0
    )
