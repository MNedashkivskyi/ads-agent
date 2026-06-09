"""FastAPI dependency for JWT authentication on protected routes.

Accepts three verification strategies (tried in order):

1. **JWKS (recommended)** — when ``SUPABASE_JWKS_URL`` is configured the
   backend fetches the public signing keys from Supabase and verifies
   the token with RS256/ES256.  No shared secret to manage.
2. **Shared secret** — when ``SUPABASE_JWT_SECRET`` is configured the
   backend verifies with HMAC (HS256/HS384/HS512).
3. **Internal JWT** — tokens signed with ``SECRET_KEY`` (used by the
   Telegram bot and internal tooling).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from jose import jwt as jose_jwt
from jose.exceptions import ExpiredSignatureError as JoseExpiredSignatureError

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_JWT_ALGORITHM = "HS256"


class _TokenExpired(Exception):
    """Raised when a structurally-valid token has simply expired.

    This is an EXPECTED condition (Supabase access tokens are short-lived),
    not a misconfiguration — the caller maps it to a clean 401 so the client
    re-authenticates, without noisy error logs.
    """


class _EmailNotConfirmed(Exception):
    """Raised when a valid Supabase token belongs to an unconfirmed email.

    Registration is complete only after the user clicks the confirmation
    link — until then the account must not be able to use the API.
    """


def _ensure_email_confirmed(payload: dict[str, object], user_id: str) -> None:
    """Reject Supabase tokens whose email is not yet confirmed.

    GoTrue copies ``email_verified`` into ``user_metadata`` and keeps it in
    sync with ``email_confirmed_at``. Only an explicit ``False`` blocks the
    request — tokens without the claim (internal tokens, other providers)
    are unaffected, so this cannot lock out legacy sessions.
    """
    meta = payload.get("user_metadata")
    if isinstance(meta, dict) and meta.get("email_verified") is False:
        # Tracked: every blocked request is logged with the user id.
        logger.warning("request rejected — email not confirmed", user_id=user_id)
        raise _EmailNotConfirmed(user_id)


# Supabase projects may use any HMAC-SHA variant.
_SUPABASE_HMAC_ALGORITHMS = ["HS256", "HS384", "HS512"]

# Asymmetric algorithms used by Supabase JWKS.
_SUPABASE_ASYMMETRIC_ALGORITHMS = ["RS256", "ES256"]

_bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# JWKS client — initialised lazily, cached for the process lifetime.
# PyJWKClient has an internal 5-min key cache so cold-start is a single
# HTTP fetch, not one per request.
# ---------------------------------------------------------------------------
_jwks_client = None  # type: ignore[assignment]


def _get_jwks_client(jwks_url: str):  # noqa: ANN202
    """Return a cached PyJWKClient for the given JWKS URL."""
    global _jwks_client  # noqa: PLW0603
    if _jwks_client is None:
        from jwt import PyJWKClient

        _jwks_client = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_client


# ---------------------------------------------------------------------------
# Token decoders
# ---------------------------------------------------------------------------


def _decode_supabase_jwks(token: str, jwks_url: str, issuer: str | None) -> str | None:
    """Verify a Supabase JWT using JWKS (public-key verification).

    Returns user_id (``sub`` claim) or ``None`` on failure.
    """
    try:
        import jwt as pyjwt

        client = _get_jwks_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)

        decode_options: dict[str, object] = {
            "verify_aud": True,
        }
        kwargs: dict[str, object] = {
            "algorithms": _SUPABASE_ASYMMETRIC_ALGORITHMS,
            "audience": "authenticated",
            "options": decode_options,
        }
        if issuer:
            kwargs["issuer"] = issuer

        payload = pyjwt.decode(token, signing_key.key, **kwargs)
        user_id = payload.get("sub")
        if user_id:
            _ensure_email_confirmed(payload, user_id)
            logger.debug("supabase jwt verified via JWKS", user_id=user_id)
        return user_id
    except pyjwt.ExpiredSignatureError as exc:
        raise _TokenExpired from exc
    except _EmailNotConfirmed:
        raise
    except Exception as exc:
        logger.debug("supabase JWKS jwt verification failed", error=str(exc))
        return None


def _decode_supabase_hmac(token: str, secret: str) -> str | None:
    """Decode a Supabase JWT using a shared HMAC secret.

    Returns user_id (``sub`` claim) or ``None`` on failure.
    """
    try:
        payload = jose_jwt.decode(
            token,
            secret,
            algorithms=_SUPABASE_HMAC_ALGORITHMS,
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if user_id:
            _ensure_email_confirmed(payload, user_id)
            logger.debug("supabase jwt verified via shared secret", user_id=user_id)
        return user_id
    except JoseExpiredSignatureError as exc:
        raise _TokenExpired from exc
    except JWTError as exc:
        logger.debug("supabase HMAC jwt verification failed", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    """Validate the Bearer JWT and return the user_id (subject claim).

    Raises HTTP 401 on missing, malformed, or expired tokens.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    # Route by the token's algorithm so we only run the matching strategy.
    # This avoids noisy cross-strategy failures (e.g. trying HMAC on an
    # asymmetric Supabase token logs "alg not allowed" every request).
    try:
        alg = str(jose_jwt.get_unverified_header(token).get("alg", ""))
    except Exception:
        alg = ""

    user_id: str | None = None
    try:
        if alg.startswith(("RS", "ES", "PS")):
            # Asymmetric → Supabase JWKS only.
            if settings.SUPABASE_JWKS_URL:
                user_id = _decode_supabase_jwks(
                    token, settings.SUPABASE_JWKS_URL, settings.SUPABASE_ISSUER
                )
        else:
            # HMAC (HS*) → Supabase shared secret, then internal SECRET_KEY.
            if settings.SUPABASE_JWT_SECRET:
                user_id = _decode_supabase_hmac(token, settings.SUPABASE_JWT_SECRET)
            if not user_id:
                try:
                    payload = jose_jwt.decode(
                        token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM]
                    )
                    user_id = payload.get("sub")
                except JoseExpiredSignatureError as exc:
                    raise _TokenExpired from exc
                except JWTError:
                    user_id = None
    except _TokenExpired as exc:
        # Expected: short-lived token expired. Clean 401, no error noise.
        logger.info("auth token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except _EmailNotConfirmed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not confirmed — please confirm your email address first",
        ) from exc

    if not user_id:
        if not (settings.SUPABASE_JWKS_URL or settings.SUPABASE_JWT_SECRET):
            logger.warning(
                "No Supabase auth configured (SUPABASE_JWKS_URL / SUPABASE_JWT_SECRET). "
                "Set SUPABASE_JWKS_URL in Railway to verify frontend tokens."
            )
        else:
            logger.warning("jwt verification failed — invalid token", alg=alg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        import sentry_sdk

        sentry_sdk.set_user({"id": user_id})
    except Exception:  # noqa: BLE001
        pass

    return user_id


CurrentUser = Annotated[str, Depends(get_current_user)]
