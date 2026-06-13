"""Claude-backed keyword generator — implements KeywordGeneratorPort.

Wraps the existing LLM client (``AnthropicClient`` / any ``LLMClient``) plus the
versioned generation prompt. On malformed JSON it retries exactly once, then
raises a clean ``LLMError`` (never leaks a parse exception to the caller).
"""

from __future__ import annotations

import json

import structlog

from adcopilot.application.ports.keyword_generator import GeneratedKeyword
from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.domain.exceptions import LLMError
from adcopilot.infrastructure.llm import json_parsing
from adcopilot.infrastructure.prompts import keyword_generation

logger = structlog.get_logger(__name__)

_VALID_INTENTS = {"BRAND", "INTENT", "PROBLEM"}
_MAX_TOKENS = 1500


class ClaudeKeywordGenerator:
    """Implements ``KeywordGeneratorPort`` against an ``LLMClient``."""

    def __init__(
        self,
        llm: LLMClient,
        prompt_repo: PromptVersionRepository | None = None,
    ) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def _resolve_templates(self) -> tuple[str | None, str | None]:
        """Load the versioned prompt from the DB; fall back to code defaults."""
        if self._prompt_repo is None:
            return None, None
        try:
            pv = await self._prompt_repo.get_latest(
                keyword_generation.KEYWORD_GENERATION_PROMPT_KEY
            )
        except Exception:  # noqa: BLE001 — prompt fetch must never break generation
            return None, None
        if pv is None:
            return None, None
        try:
            data = json.loads(pv.content)
            return data.get("system"), data.get("user_template")
        except (json.JSONDecodeError, AttributeError):
            return None, None

    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        intent_allocation: dict[str, int],
        language: str = "pl",
    ) -> list[GeneratedKeyword]:
        system_tmpl, user_tmpl = await self._resolve_templates()
        system, user = keyword_generation.render(
            service=service,
            vertical=vertical,
            problems=problems,
            intent_allocation=intent_allocation,
            language=language,
            system_template=system_tmpl,
            user_template=user_tmpl,
        )

        last_error: Exception | None = None
        for attempt in range(2):  # initial try + exactly one retry
            raw = await self._llm.complete(
                system=system, user=user, max_tokens=_MAX_TOKENS, temperature=0.4
            )
            try:
                return self._parse(raw)
            except LLMError as exc:
                last_error = exc
                logger.warning(
                    "keyword_generation.malformed_json",
                    attempt=attempt + 1,
                    error=str(exc),
                )
        raise LLMError(
            f"Keyword generation returned malformed JSON after retry: {last_error}"
        )

    @staticmethod
    def _parse(raw: str) -> list[GeneratedKeyword]:
        items = json_parsing.parse_json_array(raw)
        out: list[GeneratedKeyword] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("phrase", "")).strip().lower()
            intent = str(item.get("intent", "")).strip().upper()
            if not phrase or intent not in _VALID_INTENTS:
                continue
            if phrase in seen:
                continue
            seen.add(phrase)
            out.append(
                GeneratedKeyword(
                    phrase=phrase,
                    intent=intent,
                    reasoning=str(item.get("reasoning", "")).strip(),
                )
            )
        if not out:
            raise LLMError("No valid keyword candidates parsed from LLM output")
        return out
