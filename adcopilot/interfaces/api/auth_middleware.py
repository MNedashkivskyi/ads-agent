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

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_JWT_ALGORITHM = "HS256"

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
            logger.debug("supabase jwt verified via JWKS", user_id=user_id)
        return user_id
    except Exception as exc:
        logger.warning("supabase JWKS jwt verification failed", error=str(exc))
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
            logger.debug("supabase jwt verified via shared secret", user_id=user_id)
        return user_id
    except JWTError as exc:
        logger.warning("supabase HMAC jwt verification failed", error=str(exc))
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

    user_id: str | None = None

    # Strategy 1 — JWKS (asymmetric, recommended)
    if settings.SUPABASE_JWKS_URL:
        user_id = _decode_supabase_jwks(
            token,
            settings.SUPABASE_JWKS_URL,
            settings.SUPABASE_ISSUER,
        )

    # Strategy 2 — shared HMAC secret (legacy / fallback)
    if not user_id and settings.SUPABASE_JWT_SECRET:
        user_id = _decode_supabase_hmac(token, settings.SUPABASE_JWT_SECRET)

    # Strategy 3 — internal JWT (Telegram bot, tooling)
    if not user_id:
        try:
            payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
            user_id = payload.get("sub")
        except JWTError as exc:
            has_supabase = bool(settings.SUPABASE_JWKS_URL or settings.SUPABASE_JWT_SECRET)
            if has_supabase:
                logger.error(
                    "jwt verification failed with all configured strategies — "
                    "check SUPABASE_JWKS_URL / SUPABASE_JWT_SECRET",
                )
            else:
                logger.warning(
                    "No Supabase auth configured (SUPABASE_JWKS_URL / SUPABASE_JWT_SECRET). "
                    "Set SUPABASE_JWKS_URL in Railway to verify frontend tokens."
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

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
