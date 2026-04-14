"""OAuth state JWT — signed, single-use, short-lived.

The ``state`` parameter in the Google OAuth redirect flow protects against
CSRF.  This module wraps the token lifecycle:

* ``issue_state_jwt`` — create a signed JWT with a 15-minute expiry and a
  random ``jti``.
* ``consume_state_jwt`` — verify signature + expiry, then mark the ``jti``
  as consumed in Redis so it cannot be replayed.

Single-use semantics are enforced with Redis ``SET NX`` (atomic insert-if-
absent).  If the ``jti`` is already present, the token is rejected with
``StateAlreadyUsedError``.  The Redis key's TTL matches the JWT's
remaining validity so consumed entries expire automatically — the
"consumed jti" set cannot grow unbounded.

Note on Redis availability: unlike the rate-limit middleware we do NOT
swallow Redis errors here.  A Google OAuth callback that cannot verify
replay-protection must fail closed — the alternative is accepting a
replayed state as valid, which defeats the point.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

STATE_JWT_ALGORITHM = "HS256"
STATE_JWT_EXPIRY_MINUTES = 15
_REDIS_KEY_PREFIX = "oauth-state-used:"


class StateTokenError(Exception):
    """Base class for state-token validation failures."""


class StateTokenInvalidError(StateTokenError):
    """Bad signature, malformed payload, or expired token."""


class StateAlreadyUsedError(StateTokenError):
    """The token's ``jti`` has already been consumed — replay detected."""


@dataclass(frozen=True)
class StateClaims:
    user_id: str
    jti: str
    exp: datetime


def issue_state_jwt(
    user_id: str,
    secret_key: str,
    *,
    now: datetime | None = None,
    expiry_minutes: int = STATE_JWT_EXPIRY_MINUTES,
) -> str:
    """Mint a new state token.  ``now`` is injectable for tests."""
    current = now or datetime.now(UTC)
    payload = {
        "sub": user_id,
        "exp": current + timedelta(minutes=expiry_minutes),
        "iat": current,
        "jti": str(uuid.uuid4()),
    }
    token: str = jwt.encode(payload, secret_key, algorithm=STATE_JWT_ALGORITHM)
    return token


def _decode_state(token: str, secret_key: str) -> StateClaims:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[STATE_JWT_ALGORITHM])
    except JWTError as exc:
        raise StateTokenInvalidError("invalid or expired oauth state") from exc
    try:
        user_id: str = payload["sub"]
        jti: str = payload["jti"]
        exp_ts: int = payload["exp"]
    except KeyError as exc:
        raise StateTokenInvalidError("missing required claim") from exc
    return StateClaims(
        user_id=user_id,
        jti=jti,
        exp=datetime.fromtimestamp(exp_ts, tz=UTC),
    )


def consume_state_jwt(
    token: str,
    secret_key: str,
    *,
    redis_client: object,
    now: datetime | None = None,
) -> str:
    """Validate and *atomically* consume the token.

    Returns the ``user_id`` from the token's ``sub`` claim on success.

    Raises :class:`StateTokenInvalidError` if the signature, format, or
    expiry is wrong; :class:`StateAlreadyUsedError` if the ``jti`` has
    already been recorded in Redis.

    ``redis_client`` is typed ``object`` to avoid forcing a hard
    dependency on the ``redis`` package in unit tests.  It must expose
    the synchronous ``set(key, value, nx=True, ex=seconds)`` API.
    """
    claims = _decode_state(token, secret_key)
    current = now or datetime.now(UTC)
    ttl = int((claims.exp - current).total_seconds())
    if ttl <= 0:
        # Belt and braces — jwt.decode already enforces exp, but if an
        # injected ``now`` puts us past expiry we refuse cleanly.
        raise StateTokenInvalidError("oauth state expired")

    key = _REDIS_KEY_PREFIX + claims.jti
    # Atomic insert-if-absent.  Returns True/"OK" on success, None/False if
    # the key already exists.
    ok = redis_client.set(key, "1", nx=True, ex=ttl)  # type: ignore[attr-defined]
    if not ok:
        raise StateAlreadyUsedError("oauth state already used")
    return claims.user_id
