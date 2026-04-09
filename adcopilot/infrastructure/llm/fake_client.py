"""Fake LLM client for tests — never hits the network."""

from __future__ import annotations

_DEFAULT_RESPONSE = "This is a test explanation from the fake LLM client."


class FakeLLMClient:
    """Returns canned responses keyed by system prompt substring.

    Args:
        responses: mapping of system-prompt substrings to response strings.
            The first match wins.  Falls back to ``default`` if none match.
        default: response returned when no key matches.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str = _DEFAULT_RESPONSE,
    ) -> None:
        self._responses = responses or {}
        self._default = default
        self.calls: list[dict[str, object]] = []

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 400,
        temperature: float = 0.3,
    ) -> str:
        self.calls.append(
            {"system": system, "user": user, "max_tokens": max_tokens, "temperature": temperature}
        )
        for key, response in self._responses.items():
            if key in system:
                return response
        return self._default
