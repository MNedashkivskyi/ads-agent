"""Tests for Google Ads resilience: retry rollout + concurrency throttle (Tier-3 P3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from adcopilot.domain.exceptions import GoogleAdsRateLimited, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads import resilience
from adcopilot.infrastructure.google_ads.client import is_rate_limit_error
from adcopilot.infrastructure.google_ads.resilience import (
    ga_resilient,
    ga_throttled,
    resilient_adapter,
    throttled_adapter,
)

# --------------------------------------------------------------------------- #
# rate-limit detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "msg",
    ["RESOURCE_EXHAUSTED: quota", "Rate exceeded", "resource exhausted", "Too Many Requests"],
)
def test_is_rate_limit_error_true(msg):
    assert is_rate_limit_error(Exception(msg)) is True


def test_is_rate_limit_error_false():
    assert is_rate_limit_error(Exception("INVALID_ARGUMENT")) is False


# --------------------------------------------------------------------------- #
# ga_resilient retries; ga_throttled does not
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_ga_resilient_retries_rate_limit_then_succeeds():
    calls = {"n": 0}

    @ga_resilient("x")
    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise GoogleAdsRateLimited("quota")
        return "ok"

    with patch("asyncio.sleep", new=AsyncMock()):  # skip back-off delays
        assert await fn() == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_ga_resilient_does_not_retry_non_rate_limit():
    calls = {"n": 0}

    @ga_resilient("x")
    async def fn():
        calls["n"] += 1
        raise GoogleAdsUnavailable("boom")

    with pytest.raises(GoogleAdsUnavailable):
        await fn()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_ga_throttled_does_not_retry():
    calls = {"n": 0}

    @ga_throttled("x")
    async def fn():
        calls["n"] += 1
        raise GoogleAdsRateLimited("quota")

    with pytest.raises(GoogleAdsRateLimited):
        await fn()
    assert calls["n"] == 1  # mutations: no auto-retry (idempotency safety)


# --------------------------------------------------------------------------- #
# concurrency throttle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_throttle_bounds_concurrency(monkeypatch):
    from adcopilot.config import get_settings

    monkeypatch.setenv("GOOGLE_ADS_MAX_CONCURRENCY", "2")
    get_settings.cache_clear()
    resilience._semaphores.clear()
    try:
        state = {"cur": 0, "max": 0}

        @ga_throttled("x")
        async def fn():
            state["cur"] += 1
            state["max"] = max(state["max"], state["cur"])
            await asyncio.sleep(0.01)
            state["cur"] -= 1

        await asyncio.gather(*[fn() for _ in range(10)])
        assert state["max"] <= 2  # never more than the configured limit
    finally:
        get_settings.cache_clear()
        resilience._semaphores.clear()


# --------------------------------------------------------------------------- #
# class decorators wrap every public async method
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_resilient_adapter_wraps_and_retries():
    @resilient_adapter
    class Reader:
        def __init__(self):
            self.calls = 0

        async def fetch(self):
            self.calls += 1
            if self.calls < 2:
                raise GoogleAdsRateLimited("quota")
            return "data"

        def _private(self):  # not wrapped
            return "x"

    r = Reader()
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await r.fetch() == "data"
    assert r.calls == 2
    assert hasattr(Reader.fetch, "__wrapped__")


def test_throttled_adapter_skips_private_and_sync():
    @throttled_adapter
    class Writer:
        async def mutate(self):
            return 1

        def helper(self):  # sync — not wrapped
            return 2

    assert hasattr(Writer.mutate, "__wrapped__")
    assert not hasattr(Writer.helper, "__wrapped__")
