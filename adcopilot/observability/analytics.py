"""Pivot analytics — structured funnel/usage events (Phase 6 / T6.4).

The platform already ships structured logs (structlog) to its log sink, so
analytics are emitted as structured log events under the stable ``analytics``
logger with an ``event`` field. A log-based dashboard and alerts are built on
these events (see docs/pivot_analytics.md) — no third-party SDK is required,
which keeps PII handling simple (only ids and plan slugs are emitted).

Event taxonomy (the pivot funnel: free audit -> trial -> paid):
- ``account_connected``    — a Google Ads account was linked (top of funnel).
- ``trial_started``        — a user's trial began.
- ``subscription_changed`` — plan transition (incl. paid conversion / churn).
- ``upgrade_prompted``     — a gated capability returned 403 (upsell surface).
- ``feature_used``         — a gated capability was exercised (per-tier usage).
"""

from __future__ import annotations

from typing import Any

import structlog

_analytics = structlog.get_logger("analytics")


def emit(event: str, **props: Any) -> None:
    """Emit a structured analytics event. Never raises — analytics must not
    break a user request."""
    try:
        _analytics.info("analytics", event=event, **props)
    except Exception:  # noqa: BLE001 — analytics is best-effort
        pass


def trial_started(user_id: str) -> None:
    emit("trial_started", user_id=user_id)


def account_connected(user_id: str, account_id: str) -> None:
    emit("account_connected", user_id=user_id, account_id=account_id)


def subscription_changed(user_id: str, old_plan: str | None, new_plan: str, status: str) -> None:
    emit(
        "subscription_changed",
        user_id=user_id,
        old_plan=old_plan,
        new_plan=new_plan,
        status=status,
        paid_conversion=(
            old_plan in (None, "starter") and new_plan in ("professional", "business")
        ),
    )


def upgrade_prompted(user_id: str, plan: str, capability: str) -> None:
    emit("upgrade_prompted", user_id=user_id, plan=plan, capability=capability)


def feature_used(user_id: str, plan: str, capability: str) -> None:
    emit("feature_used", user_id=user_id, plan=plan, capability=capability)


# --- Free-audit funnel (Audit Funnel) -------------------------------------
# The acquisition funnel before the pivot funnel above: connect -> scan ->
# reveal -> signup. Only ids are emitted (no PII).


def audit_started(audit_session_id: str, source: str) -> None:
    emit("audit_started", audit_session_id=audit_session_id, source=source)


def audit_scan_completed(audit_session_id: str, report_id: str | None) -> None:
    emit("audit_scan_completed", audit_session_id=audit_session_id, report_id=report_id)


def audit_scan_failed(audit_session_id: str, reason: str) -> None:
    emit("audit_scan_failed", audit_session_id=audit_session_id, reason=reason)


def audit_report_viewed(report_id: str) -> None:
    emit("audit_report_viewed", report_id=report_id)


def audit_session_promoted(audit_session_id: str, user_id: str) -> None:
    emit("audit_session_promoted", audit_session_id=audit_session_id, user_id=user_id)
