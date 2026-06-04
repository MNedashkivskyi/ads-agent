"""Retry/back-off helper for Google Ads rate-limit (quota) errors.

Google Ads returns RESOURCE_EXHAUSTED when per-minute/day quotas are hit. The
query/keyword-planner layers map that to :class:`GoogleAdsRateLimited`. This
helper retries such calls with bounded exponential back-off. It does NOT retry
auth or generic-unavailable errors (those are not transient quota issues).

Deterministic jitter (derived from the attempt index, not RNG) keeps it usable
in environments where wall-clock randomness is unavailable.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog

from adcopilot.domain.exceptions import GoogleAdsRateLimited

logger = structlog.get_logger(__name__)

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BASE_DELAY = 2.0  # seconds; grows 2s, 4s, 8s ...
_MAX_DELAY = 30.0


async def retry_on_rate_limit[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = _DEFAULT_ATTEMPTS,
    base_delay: float = _DEFAULT_BASE_DELAY,
    label: str = "google_ads_call",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Call ``fn`` (a zero-arg async thunk), retrying on GoogleAdsRateLimited.

    ``sleep`` is injectable so tests run without real delays. Re-raises the last
    GoogleAdsRateLimited after ``attempts`` exhausted; non-rate-limit errors
    propagate immediately.
    """
    last_exc: GoogleAdsRateLimited | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except GoogleAdsRateLimited as exc:
            last_exc = exc
            if attempt == attempts - 1:
                break
            delay = min(base_delay * (2**attempt), _MAX_DELAY)
            logger.warning(
                "google_ads_rate_limited_retrying",
                label=label,
                attempt=attempt + 1,
                max_attempts=attempts,
                delay_seconds=delay,
            )
            await sleep(delay)
    assert last_exc is not None
    raise last_exc
