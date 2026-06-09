"""Tokens for unconfirmed emails must be rejected (403) and tracked."""

from __future__ import annotations

import pytest
from jose import jwt as jose_jwt

from adcopilot.interfaces.api.auth_middleware import (
    _decode_supabase_hmac,
    _EmailNotConfirmed,
    _ensure_email_confirmed,
)

_SECRET = "test-supabase-secret"


def _token(metadata: dict | None) -> str:
    payload: dict[str, object] = {"sub": "user-123"}
    if metadata is not None:
        payload["user_metadata"] = metadata
    return jose_jwt.encode(payload, _SECRET, algorithm="HS256")


def test_unconfirmed_email_raises() -> None:
    with pytest.raises(_EmailNotConfirmed):
        _decode_supabase_hmac(_token({"email_verified": False}), _SECRET)


def test_confirmed_email_passes() -> None:
    assert _decode_supabase_hmac(_token({"email_verified": True}), _SECRET) == "user-123"


def test_missing_claim_passes() -> None:
    # Internal tokens / other providers have no user_metadata — must not block.
    assert _decode_supabase_hmac(_token(None), _SECRET) == "user-123"


def test_ensure_helper_only_blocks_explicit_false() -> None:
    _ensure_email_confirmed({"user_metadata": {}}, "u")
    _ensure_email_confirmed({"user_metadata": {"email_verified": True}}, "u")
    _ensure_email_confirmed({}, "u")
    with pytest.raises(_EmailNotConfirmed):
        _ensure_email_confirmed({"user_metadata": {"email_verified": False}}, "u")
