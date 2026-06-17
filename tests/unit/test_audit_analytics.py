"""The audit-funnel analytics events must never raise (Audit Funnel hardening)."""

from __future__ import annotations

from adcopilot.observability import analytics


def test_audit_funnel_events_do_not_raise() -> None:
    analytics.audit_started("s1", "landing")
    analytics.audit_scan_completed("s1", "rep-1")
    analytics.audit_scan_completed("s1", None)
    analytics.audit_scan_failed("s1", "token_missing")
    analytics.audit_report_viewed("rep-1")
    analytics.audit_session_promoted("s1", "u1")
