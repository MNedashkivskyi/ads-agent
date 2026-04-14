"""Path-prefix rate limiting middleware.

slowapi's ``@limiter.limit`` decorator is great for one-off per-endpoint
limits (we already use it on ``/api/auth/login`` and ``/api/auth/signup``),
but the security hardening spec requires *blanket* limits on whole URL
prefixes:

====================  ==========================
prefix                 limit (per source IP)
====================  ==========================
``/oauth/*``           ``10/minute``
``/api/*``             ``60/minute``
``/webhooks/*``        ``100/minute``
``/telegram/webhook``  ``100/minute`` (treated as a webhook)
====================  ==========================

Decorating every route handler individually would be brittle — new routes
would silently bypass the limit.  Instead we run a single middleware that
picks the longest-matching prefix and hits the rate-limit storage directly
via the ``limits`` library (which is already a slowapi dependency).

This middleware is independent from slowapi's own ``SlowAPIMiddleware``.
The slowapi decorators continue to apply their tighter per-endpoint limits
(e.g. ``5/minute`` on auth); the prefix middleware adds the outer envelope.
"""

from __future__ import annotations

from dataclasses import dataclass

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage as AsyncMemoryStorage
from limits.aio.storage import RedisStorage as AsyncRedisStorage
from limits.aio.storage import Storage as AsyncStorage
from limits.aio.strategies import FixedWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class PrefixRateLimitConfig:
    """One rate-limit rule keyed by URL path prefix.

    ``prefix`` matches with ``request.url.path.startswith(prefix)``.  Longer
    prefixes win on ties (see :class:`PathPrefixRateLimitMiddleware`), so
    ``/api/webhooks/stripe`` can be given its own limit without being
    shadowed by ``/api/``.
    """

    prefix: str
    limit: str  # e.g. "60/minute"


def build_default_prefix_rate_limits() -> list[PrefixRateLimitConfig]:
    """Default limits required by the security-hardening spec.

    Kept in its own function so tests can assert the exact rule set and
    ``main.py`` doesn't need to re-declare the values.
    """
    return [
        PrefixRateLimitConfig(prefix="/oauth/", limit="10/minute"),
        PrefixRateLimitConfig(prefix="/webhooks/", limit="100/minute"),
        PrefixRateLimitConfig(prefix="/telegram/webhook", limit="100/minute"),
        # The broadest /api/ limit goes last so longer, more specific prefixes
        # above win during the longest-match lookup.
        PrefixRateLimitConfig(prefix="/api/", limit="60/minute"),
    ]


def _get_client_ip(request: Request) -> str:
    """Mirror the IP-extraction logic from ``adcopilot.rate_limit``.

    We do not import ``_get_real_ip`` from that module because it expects a
    slowapi-style request wrapper; Starlette's ``Request`` has the same
    ``headers`` / ``client`` surface so inlining is clearer and avoids a
    circular import.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _storage_for_uri(uri: str) -> AsyncStorage:
    """Build an async limits storage backend from a Redis URI.

    ``memory://`` is used by tests; everything else goes to Redis.  We use
    the async storage variants because Starlette middleware is async.
    """
    if uri.startswith("memory"):
        return AsyncMemoryStorage()
    return AsyncRedisStorage(uri)


class PathPrefixRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply a per-IP rate limit based on the longest matching path prefix.

    Construction does not open any network connections; storage is created
    lazily on first request so tests that never trigger a request don't need
    Redis either.
    """

    def __init__(
        self,
        app: object,
        *,
        storage_uri: str,
        configs: list[PrefixRateLimitConfig] | None = None,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._storage_uri = storage_uri
        self._configs: list[tuple[str, RateLimitItem]] = [
            (c.prefix, parse(c.limit))
            for c in (configs or build_default_prefix_rate_limits())
        ]
        # Sort by prefix length descending so the first match is the most
        # specific — e.g. "/telegram/webhook" wins over a hypothetical
        # "/telegram/" rule.
        self._configs.sort(key=lambda pair: len(pair[0]), reverse=True)
        self._storage: AsyncStorage | None = None
        self._limiter: FixedWindowRateLimiter | None = None

    def _ensure_backend(self) -> FixedWindowRateLimiter:
        if self._limiter is None:
            self._storage = _storage_for_uri(self._storage_uri)
            self._limiter = FixedWindowRateLimiter(self._storage)
        return self._limiter

    def _match(self, path: str) -> tuple[str, RateLimitItem] | None:
        for prefix, item in self._configs:
            if path.startswith(prefix):
                return prefix, item
        return None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        match = self._match(request.url.path)
        if match is None:
            return await call_next(request)

        prefix, item = match
        ip = _get_client_ip(request)
        # Namespace the counter key by prefix so limits on different prefixes
        # do not share a window.
        key = f"prefix-rate-limit:{prefix}:{ip}"

        try:
            limiter_backend = self._ensure_backend()
            allowed = await limiter_backend.hit(item, key)
        except Exception:
            # Availability over security — if Redis is unavailable we do not
            # want to 500 every request.  Mirrors ``swallow_errors=True`` on
            # the slowapi limiter.
            return await call_next(request)

        if not allowed:
            retry_after = str(item.get_expiry())
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {item}"},
                headers={"Retry-After": retry_after},
            )
        return await call_next(request)
