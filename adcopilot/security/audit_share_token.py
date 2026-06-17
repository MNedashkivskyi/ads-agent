"""Signed shareable-link tokens for audit reports (Audit Funnel T2.4).

Unlike the OAuth state token, a share link is NOT single-use — the recipient
(e.g. an agency's prospect) may open it repeatedly until it expires. So there is
no Redis replay check: a signed, expiring JWT carrying the report id suffices.
The token is what unlocks the full (un-gated) report for a non-owner.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

_ALG = "HS256"
_SCOPE = "audit-share"
DEFAULT_EXPIRY_DAYS = 30


class ShareTokenInvalid(Exception):
    """Bad signature, wrong scope, malformed, or expired share token."""


def issue_share_token(
    report_id: str,
    secret_key: str,
    *,
    now: datetime | None = None,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> str:
    current = now or datetime.now(UTC)
    payload = {
        "sub": report_id,
        "scope": _SCOPE,
        "iat": current,
        "exp": current + timedelta(days=expiry_days),
    }
    return jwt.encode(payload, secret_key, algorithm=_ALG)


def verify_share_token(token: str, secret_key: str) -> str:
    """Return the report id a valid token unlocks, or raise ShareTokenInvalid."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_ALG])
    except JWTError as exc:
        raise ShareTokenInvalid("invalid or expired share token") from exc
    if payload.get("scope") != _SCOPE or "sub" not in payload:
        raise ShareTokenInvalid("not an audit-share token")
    return str(payload["sub"])
