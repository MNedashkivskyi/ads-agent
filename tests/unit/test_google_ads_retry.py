"""Unit tests for the Google Ads rate-limit retry helper."""

from __future__ import annotations

import pytest

from adcopilot.domain.exceptions import GoogleAdsRateLimited, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.retry import retry_on_rate_limit


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.mark.asyncio
async def test_returns_immediately_on_success():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        return "ok"

    result = await retry_on_rate_limit(fn, sleep=_noop_sleep)
    assert result == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise GoogleAdsRateLimited("resource exhausted")
        return "recovered"

    result = await retry_on_rate_limit(fn, attempts=3, sleep=_noop_sleep)
    assert result == "recovered"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_raises_after_attempts_exhausted():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise GoogleAdsRateLimited("quota")

    with pytest.raises(GoogleAdsRateLimited):
        await retry_on_rate_limit(fn, attempts=3, sleep=_noop_sleep)
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_non_rate_limit_error_not_retried():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        raise GoogleAdsUnavailable("boom")

    with pytest.raises(GoogleAdsUnavailable):
        await retry_on_rate_limit(fn, attempts=3, sleep=_noop_sleep)
    assert calls["n"] == 1  # not retried


@pytest.mark.asyncio
async def test_backoff_delays_are_exponential():
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def fn():
        raise GoogleAdsRateLimited("quota")

    with pytest.raises(GoogleAdsRateLimited):
        await retry_on_rate_limit(fn, attempts=4, base_delay=2.0, sleep=record_sleep)
    # 3 sleeps between 4 attempts: 2, 4, 8
    assert delays == [2.0, 4.0, 8.0]
