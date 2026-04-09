"""Unit tests for LLM client port adapters."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from adcopilot.domain.exceptions import LLMError
from adcopilot.infrastructure.llm.fake_client import FakeLLMClient

# ---------------------------------------------------------------------------
# FakeLLMClient tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_client_returns_default_when_no_match() -> None:
    client = FakeLLMClient(default="default response")
    result = await client.complete(system="some system", user="some user")
    assert result == "default response"


@pytest.mark.asyncio
async def test_fake_client_returns_canned_response_on_match() -> None:
    client = FakeLLMClient(responses={"Google Ads": "matched response"})
    result = await client.complete(system="Explain Google Ads recommendations", user="user")
    assert result == "matched response"


@pytest.mark.asyncio
async def test_fake_client_falls_back_to_default_when_no_key_matches() -> None:
    client = FakeLLMClient(responses={"XYZ": "won't match"}, default="fallback")
    result = await client.complete(system="something else", user="u")
    assert result == "fallback"


@pytest.mark.asyncio
async def test_fake_client_records_calls() -> None:
    client = FakeLLMClient()
    await client.complete(system="sys", user="usr", max_tokens=200, temperature=0.5)
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == "sys"
    assert client.calls[0]["user"] == "usr"
    assert client.calls[0]["max_tokens"] == 200
    assert client.calls[0]["temperature"] == 0.5


@pytest.mark.asyncio
async def test_fake_client_first_matching_key_wins() -> None:
    client = FakeLLMClient(responses={"ads": "first", "Google": "second"})
    result = await client.complete(system="Google ads advice", user="u")
    # "ads" appears in "Google ads advice" — first match wins
    assert result == "first"


# ---------------------------------------------------------------------------
# AnthropicClient retry tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_client_retries_on_429_then_succeeds() -> None:
    """Client should retry on RateLimitError and succeed on third attempt."""
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    call_count = 0

    async def _fake_create(**kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise anthropic.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body={},
            )
        mock_block = MagicMock()
        mock_block.text = "success after retries"
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        return mock_response

    client = AnthropicClient(api_key="test-key")
    client._client.messages.create = _fake_create  # type: ignore[method-assign]

    result = await client.complete(system="sys", user="user")
    assert result == "success after retries"
    assert call_count == 3


@pytest.mark.asyncio
async def test_anthropic_client_raises_llm_error_on_timeout() -> None:
    """asyncio.TimeoutError should be wrapped in LLMError."""
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    async def _slow_create(**kwargs: object) -> object:
        await asyncio.sleep(9999)
        return MagicMock()

    client = AnthropicClient(api_key="test-key")
    client._client.messages.create = _slow_create  # type: ignore[method-assign]

    # Patch the timeout to 0 so it fires immediately
    with patch("adcopilot.infrastructure.llm.anthropic_client._TIMEOUT_SECONDS", 0.01), pytest.raises(LLMError, match="timed out"):
        await client.complete(system="s", user="u")


@pytest.mark.asyncio
async def test_anthropic_client_raises_llm_error_on_api_error() -> None:
    """Non-retryable APIError should be wrapped in LLMError."""
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    async def _error_create(**kwargs: object) -> object:
        raise anthropic.APIConnectionError(request=MagicMock())

    client = AnthropicClient(api_key="test-key")
    client._client.messages.create = _error_create  # type: ignore[method-assign]

    with pytest.raises(LLMError):
        await client.complete(system="s", user="u")
