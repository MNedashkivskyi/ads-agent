"""FastAPI dependency for JWT authentication on protected routes.

Accepts two token types:
1. Supabase-issued JWTs (signed with SUPABASE_JWT_SECRET) — used by the web frontend.
   The user_id is taken from the ``sub`` claim.
2. Internal JWTs (signed with SECRET_KEY) — used by the Telegram bot and internal tooling.

The middleware tries Supabase verification first when SUPABASE_JWT_SECRET is configured,
then falls back to the internal secret.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from adcopilot.config import Settings, get_settings

logger = structlog.get_logger(__name__)

_JWT_ALGORITHM = "HS256"

# Supabase projects may use any HMAC-SHA variant depending on project
# settings.  We accept all three so a project-level algorithm change
# doesn't silently break auth.
_SUPABASE_ALGORITHMS = ["HS256", "HS384", "HS512"]

_bearer = HTTPBearer(auto_error=False)


def _decode_supabase_token(token: str, secret: str) -> str | None:
    """Decode a Supabase JWT. Returns user_id (sub claim) or None on failure."""
    try:
        # Log the token header's alg for diagnostics (unverified peek).
        try:
            header = jwt.get_unverified_header(token)
            token_alg = header.get("alg", "unknown")
        except Exception:
            token_alg = "unreadable"

        payload = jwt.decode(
            token,
            secret,
            algorithms=_SUPABASE_ALGORITHMS,
            options={"verify_aud": False},
        )
        user_id = payload.get("sub")
        if user_id:
            logger.debug("supabase jwt verified", user_id=user_id, alg=token_alg)
        return user_id
    except JWTError as exc:
        logger.warning(
            "supabase jwt verification failed",
            error=str(exc),
            token_alg=token_alg,
        )
        return None


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

    # Try Supabase JWT first when secret is configured
    if settings.SUPABASE_JWT_SECRET:
        user_id = _decode_supabase_token(token, settings.SUPABASE_JWT_SECRET)
    else:
        logger.warning(
            "SUPABASE_JWT_SECRET is not configured — Supabase tokens will not be verified. "
            "Set this env var in Railway to the JWT secret from Supabase → Settings → API."
        )

    # Fall back to internal JWT secret
    if not user_id:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[_JWT_ALGORITHM])
            user_id = payload.get("sub")
        except JWTError as exc:
            # If Supabase secret was configured but decode failed, the token is
            # likely a Supabase token with a wrong/rotated secret.  Surface that
            # in the error so operators can diagnose faster.
            if settings.SUPABASE_JWT_SECRET:
                logger.error(
                    "jwt verification failed with both Supabase and internal secrets — "
                    "check that SUPABASE_JWT_SECRET matches your Supabase project",
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
