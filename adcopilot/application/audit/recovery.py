"""Recovery-meter reconciliation (Audit Funnel — retention loop / Phase 4).

When a fix is applied we book its *projected* monthly saving to the recovery
ledger immediately, so the meter moves and reinforces the audit's promise. A
settle task later reconciles that to a *measured* saving by checking how much of
the flagged spend actually disappeared. This module holds the pure reconciliation
arithmetic so it stays fully unit-testable, with no database or Google Ads API.
"""

from __future__ import annotations


def reconcile_realized_saving(
    *, projected_micros: int, baseline_cost_micros: int, post_cost_micros: int
) -> int:
    """Measured saving = the projection, scaled by the share of flagged spend eliminated.

    Waste-elimination fixes (pause keyword, add negative, pause campaign, …) drive
    the flagged entity's spend toward zero, so the realised saving is ~= the
    projection. If the spend did *not* drop (the fix was reverted or ineffective)
    the credited saving scales down toward zero. Clamped to ``[0, projected]``.

    ``baseline_cost_micros`` is the entity's spend over the pre-apply window and
    ``post_cost_micros`` over an equal post-apply window. With no pre-apply spend
    to compare against we trust the projection.
    """
    if projected_micros <= 0:
        return 0
    if baseline_cost_micros <= 0:
        return projected_micros
    eliminated = (baseline_cost_micros - post_cost_micros) / baseline_cost_micros
    eliminated = max(0.0, min(1.0, eliminated))
    return int(round(projected_micros * eliminated))
