"""Tests for :mod:`adcopilot.security.oauth_state`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from adcopilot.security.oauth_state import (
    STATE_JWT_ALGORITHM,
    STATE_JWT_EXPIRY_MINUTES,
    StateAlreadyUsedError,
    StateTokenInvalidError,
    consume_state_jwt,
    issue_state_jwt,
)

_SECRET = "test-secret-key-unit"
_USER = "user-123"


class FakeRedis:
    """Minimal in-memory stand-in for ``redis.Redis`` with SET NX support."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int | None]] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = (value, ex)
        return True


# ---------------------------------------------------------------------------
# issue_state_jwt
# ---------------------------------------------------------------------------


def test_issue_state_jwt_has_15_minute_expiry_by_default() -> None:
    assert STATE_JWT_EXPIRY_MINUTES == 15
    now = datetime.now(UTC)
    token = issue_state_jwt(_USER, _SECRET, now=now)
    payload = jwt.decode(token, _SECRET, algorithms=[STATE_JWT_ALGORITHM])
    exp_dt = datetime.fromtimestamp(payload["exp"], tz=UTC)
    # exp is stored as an integer unix timestamp so microseconds are dropped —
    # compare with a 2-second tolerance for the encode roundtrip.
    expected = now + timedelta(minutes=15)
    assert abs((exp_dt - expected).total_seconds()) < 2


def test_issue_state_jwt_has_random_jti() -> None:
    t1 = issue_state_jwt(_USER, _SECRET)
    t2 = issue_state_jwt(_USER, _SECRET)
    p1 = jwt.decode(t1, _SECRET, algorithms=[STATE_JWT_ALGORITHM])
    p2 = jwt.decode(t2, _SECRET, algorithms=[STATE_JWT_ALGORITHM])
    assert p1["jti"] != p2["jti"]


def test_issue_state_jwt_encodes_user_id_as_subject() -> None:
    token = issue_state_jwt("alice", _SECRET)
    payload = jwt.decode(token, _SECRET, algorithms=[STATE_JWT_ALGORITHM])
    assert payload["sub"] == "alice"


# ---------------------------------------------------------------------------
# consume_state_jwt — happy path
# ---------------------------------------------------------------------------


def test_consume_returns_user_id_on_first_use() -> None:
    redis = FakeRedis()
    token = issue_state_jwt(_USER, _SECRET)
    assert consume_state_jwt(token, _SECRET, redis_client=redis) == _USER
    # Side-effect: jti recorded in Redis with a TTL near 15*60s.
    assert len(redis.store) == 1
    ((_key, (_val, ttl)),) = redis.store.items()
    assert ttl is not None
    assert 0 < ttl <= 15 * 60


# ---------------------------------------------------------------------------
# consume_state_jwt — single-use enforcement (acceptance criterion)
# ---------------------------------------------------------------------------


def test_consume_second_use_raises_state_already_used() -> None:
    """Acceptance: a captured state JWT cannot be replayed after use."""
    redis = FakeRedis()
    token = issue_state_jwt(_USER, _SECRET)

    # First use succeeds.
    consume_state_jwt(token, _SECRET, redis_client=redis)

    # Second use with the same token must be rejected.
    with pytest.raises(StateAlreadyUsedError):
        consume_state_jwt(token, _SECRET, redis_client=redis)


def test_different_tokens_do_not_collide() -> None:
    redis = FakeRedis()
    t1 = issue_state_jwt("alice", _SECRET)
    t2 = issue_state_jwt("bob", _SECRET)
    assert consume_state_jwt(t1, _SECRET, redis_client=redis) == "alice"
    assert consume_state_jwt(t2, _SECRET, redis_client=redis) == "bob"


# ---------------------------------------------------------------------------
# consume_state_jwt — rejections
# ---------------------------------------------------------------------------


def test_consume_rejects_tampered_signature() -> None:
    redis = FakeRedis()
    token = issue_state_jwt(_USER, _SECRET)
    # Flip a character in the signature.
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(StateTokenInvalidError):
        consume_state_jwt(bad, _SECRET, redis_client=redis)


def test_consume_rejects_wrong_secret() -> None:
    redis = FakeRedis()
    token = issue_state_jwt(_USER, _SECRET)
    with pytest.raises(StateTokenInvalidError):
        consume_state_jwt(token, "a-different-secret", redis_client=redis)


def test_consume_rejects_expired_token_via_jose() -> None:
    redis = FakeRedis()
    past = datetime.now(UTC) - timedelta(minutes=30)
    token = issue_state_jwt(_USER, _SECRET, now=past)
    with pytest.raises(StateTokenInvalidError):
        consume_state_jwt(token, _SECRET, redis_client=redis)


def test_consume_rejects_token_with_missing_claim() -> None:
    redis = FakeRedis()
    payload = {"sub": _USER, "exp": datetime.now(UTC) + timedelta(minutes=5)}  # no jti
    token: str = jwt.encode(payload, _SECRET, algorithm=STATE_JWT_ALGORITHM)
    with pytest.raises(StateTokenInvalidError):
        consume_state_jwt(token, _SECRET, redis_client=redis)


def test_ttl_uses_remaining_seconds_not_full_window() -> None:
    """If the token is issued 10 min ago with 15 min total, TTL is about 5 min."""
    redis = FakeRedis()
    issued_at = datetime.now(UTC) - timedelta(minutes=10)
    token = issue_state_jwt(_USER, _SECRET, now=issued_at)
    consume_state_jwt(token, _SECRET, redis_client=redis)
    ((_key, (_val, ttl)),) = redis.store.items()
    assert ttl is not None
    # ~5 minutes remaining; allow wall-clock slack.
    assert 4 * 60 <= ttl <= 6 * 60
