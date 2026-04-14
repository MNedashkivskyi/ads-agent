"""Debug / diagnostics endpoints.

These are always mounted but intentionally cheap and side-effect-free so
they can safely stay in production — used to verify observability plumbing
end-to-end without deploying a special build.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


class SentryDebugError(RuntimeError):
    """Deliberate error raised by :func:`trigger_sentry` to verify wiring."""


@router.get("/sentry")
async def trigger_sentry() -> None:
    """Raise a ``SentryDebugError`` so the Sentry integration can be verified.

    Used during onboarding to confirm the DSN is reachable and the
    before_send hook does not drop events.  Returns nothing on success —
    the caller is expected to see a 500 in their browser and a matching
    event in the Sentry dashboard within ~10 seconds.
    """
    logger.warning("debug sentry endpoint hit — raising deliberate error")
    raise SentryDebugError("Deliberate test error from /debug/sentry — Sentry integration check.")
