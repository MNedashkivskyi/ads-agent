"""Unit tests for audit share tokens (Audit Funnel T2.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from adcopilot.security.audit_share_token import (
    ShareTokenInvalid,
    issue_share_token,
    verify_share_token,
)

_SECRET = "test-secret"


def test_issue_then_verify_roundtrips_report_id() -> None:
    token = issue_share_token("rep-1", _SECRET)
    assert verify_share_token(token, _SECRET) == "rep-1"


def test_wrong_secret_rejected() -> None:
    token = issue_share_token("rep-1", _SECRET)
    with pytest.raises(ShareTokenInvalid):
        verify_share_token(token, "other-secret")


def test_expired_token_rejected() -> None:
    past = datetime.now(UTC) - timedelta(days=40)
    token = issue_share_token("rep-1", _SECRET, now=past, expiry_days=30)
    with pytest.raises(ShareTokenInvalid):
        verify_share_token(token, _SECRET)


def test_token_without_share_scope_rejected() -> None:
    from jose import jwt

    bad = jwt.encode({"sub": "rep-1"}, _SECRET, algorithm="HS256")
    with pytest.raises(ShareTokenInvalid):
        verify_share_token(bad, _SECRET)
