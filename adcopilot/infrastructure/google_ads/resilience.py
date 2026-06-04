"""Resilience for outbound Google Ads API calls: concurrency throttle + retry.

Two class decorators wrap every public async method of an adapter:

- ``throttled_adapter`` — bounds concurrency (a per-event-loop semaphore) so
  managing many accounts at once can't exhaust the developer-token quota.
- ``resilient_adapter`` — throttle **plus** ``retry_on_rate_limit`` back-off.
  Use ONLY on idempotent read adapters: retrying a method that issues multiple
  mutate calls (e.g. two-phase asset creation) could double-apply, so mutation
  adapters get throttle-only and surface quota errors as ``GoogleAdsRateLimited``
  for callers to handle.

The semaphore is keyed by the running event loop (Celery tasks each call
``asyncio.run``, creating a fresh loop) so it never binds across loops.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import TypeVar

from adcopilot.infrastructure.google_ads.retry import retry_on_rate_limit

T = TypeVar("T")

# One semaphore per event loop. WeakKeyDictionary so finished loops are GC'd.
_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _get_semaphore() -> asyncio.Semaphore:
    from adcopilot.config import get_settings

    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        limit = max(1, get_settings().GOOGLE_ADS_MAX_CONCURRENCY)
        sem = asyncio.Semaphore(limit)
        _semaphores[loop] = sem
    return sem


def ga_throttled(
    label: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Bound concurrency of an async GA call (no retry)."""

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            async with _get_semaphore():
                return await fn(*args, **kwargs)

        return wrapper

    return deco


def ga_resilient(
    label: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Throttle + retry an async GA call (idempotent reads only)."""

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> T:
            async with _get_semaphore():
                return await retry_on_rate_limit(lambda: fn(*args, **kwargs), label=label)

        return wrapper

    return deco


def _wrap_public_async_methods(cls: type, decorator_factory) -> type:
    for name, attr in list(cls.__dict__.items()):
        if name.startswith("_") or not inspect.iscoroutinefunction(attr):
            continue
        setattr(cls, name, decorator_factory(f"{cls.__name__}.{name}")(attr))
    return cls


def throttled_adapter(cls: type) -> type:
    """Class decorator: throttle every public async method (mutation adapters)."""
    return _wrap_public_async_methods(cls, ga_throttled)


def resilient_adapter(cls: type) -> type:
    """Class decorator: throttle + retry every public async method (read adapters)."""
    return _wrap_public_async_methods(cls, ga_resilient)
