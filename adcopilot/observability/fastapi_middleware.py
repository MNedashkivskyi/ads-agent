"""FastAPI middleware that propagates request identity into Sentry context.

The middleware runs for every request and:

1. Resets the request-scoped context vars (so stale values from the worker's
   previous request cannot leak).
2. If the request carries a valid Bearer JWT, decodes ``sub`` and sets the
   user tag.  Decode failures are silent — auth errors are handled downstream
   by the actual auth dependencies.

This has to be a separate middleware (rather than a dependency) because we
want the tag present on 4xx/5xx responses from dependency-level failures
(e.g. rate-limit rejection, validation errors) too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from adcopilot.observability.sentry import clear_context, set_user_context

logger = structlog.get_logger(__name__)


class SentryContextMiddleware(BaseHTTPMiddleware):
    """Tag each request with ``user_id`` when a Bearer JWT is present."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        clear_context()

        auth_header = request.headers.get("Authorization")
        user_id = _extract_user_id_from_jwt(auth_header)
        if user_id is not None:
            set_user_context(user_id)

        return await call_next(request)


def _extract_user_id_from_jwt(auth_header: str | None) -> str | None:
    """Return the ``sub`` claim from a Bearer JWT, or ``None`` on any failure.

    This MUST NOT raise — observability is never allowed to break a request.
    We also skip signature verification: the tag is informational, and the
    actual auth dependency will reject invalid tokens before any handler runs.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from jose import jwt

        payload = jwt.get_unverified_claims(token)
        sub = payload.get("sub")
        return str(sub) if sub else None
    except Exception:
        return None
