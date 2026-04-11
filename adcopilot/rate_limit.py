"""Rate limiter singleton used by API endpoints.

The limiter is backed by the project's Redis instance so limits are
shared across all uvicorn worker processes.  If Redis is temporarily
unavailable, ``swallow_errors=True`` causes limits to be skipped rather
than returning a 500 — a deliberate availability-over-security trade-off
(Redis is already required for Celery; a Redis outage is a larger incident).

Usage in route handlers
-----------------------
.. code-block:: python

    from fastapi import Request
    from adcopilot.rate_limit import limiter

    @router.post("/some-endpoint")
    @limiter.limit("5/minute")
    async def my_endpoint(request: Request, ...) -> ...:
        ...

Registering with FastAPI
------------------------
See ``adcopilot/main.py`` — the limiter is attached to ``app.state``
and the ``SlowAPIMiddleware`` + ``RateLimitExceeded`` handler are added
there.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter


def _get_real_ip(request: Request) -> str:
    """Extract the real client IP, respecting standard proxy headers.

    Caddy sets ``X-Real-IP``; nginx typically sets ``X-Forwarded-For``.
    Falls back to the direct connection address for local development.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _create_limiter() -> Limiter:
    from adcopilot.config import get_settings

    settings = get_settings()
    return Limiter(
        key_func=_get_real_ip,
        storage_uri=settings.REDIS_URL,
        # Add X-RateLimit-* / Retry-After headers so clients can back off gracefully.
        headers_enabled=True,
        # If Redis is unavailable, skip rate limiting rather than return 500.
        swallow_errors=True,
    )


limiter: Limiter = _create_limiter()
