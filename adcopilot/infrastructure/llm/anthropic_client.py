"""Anthropic LLM adapter with retry and timeout."""

from __future__ import annotations

import asyncio
import logging

import anthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from adcopilot.domain.exceptions import LLMError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_TIMEOUT_SECONDS = 15.0


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, anthropic.RateLimitError) or (
        isinstance(exc, anthropic.APIStatusError) and exc.status_code in _RETRYABLE_STATUS_CODES
    )


class AnthropicClient:
    """Async Anthropic adapter implementing LLMClient protocol."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def aclose(self) -> None:
        """Close the underlying async HTTP client.

        Must be called before the running event loop is closed; otherwise the
        httpx client is torn down during GC on an already-closed loop, raising
        a noisy ``RuntimeError: Event loop is closed``.
        """
        try:
            await self._client.close()
        except Exception:  # pragma: no cover - best-effort cleanup
            logger.debug("AnthropicClient.aclose failed", exc_info=True)

    async def __aenter__(self) -> AnthropicClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> str:
        """Call the Anthropic Messages API with retry and timeout."""
        try:
            return await self._complete_with_retry(
                system=system, user=user, max_tokens=max_tokens, temperature=temperature
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
    )
    async def _complete_with_retry(
        self,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        try:
            response = await asyncio.wait_for(
                self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                ),
                timeout=_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise LLMError("LLM request timed out") from exc

        block = response.content[0]
        if hasattr(block, "text"):
            return str(block.text)
        raise LLMError("Unexpected response block type from Anthropic API")
