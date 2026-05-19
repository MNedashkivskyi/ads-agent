"""GenerateWeeklyInsightUseCase — produces one-paragraph strategic observation from account context."""

from __future__ import annotations

import json
from typing import Any

import structlog

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "weekly_insight_v1"
_SYSTEM = (
    "Jesteś strategicznym doradcą Google Ads pomagającym polskim właścicielom firm MŚP. "
    "Odpowiadaj wyłącznie po polsku. Cytuj tylko liczby z dostarczonych danych."
)


class GenerateWeeklyInsightUseCase:
    def __init__(self, llm: LLMClient, prompt_repo: PromptVersionRepository) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def execute(self, account_context: dict[str, Any]) -> str:
        """Generate one strategic paragraph in Polish for the given account context."""
        context_json = json.dumps(account_context, ensure_ascii=False, indent=2)
        prompt_template = await get_latest_prompt(self._prompt_repo, _PROMPT_KEY)
        user_msg = prompt_template.format(account_context=context_json)

        insight = await self._llm.complete(
            system=_SYSTEM,
            user=user_msg,
            max_tokens=500,
            temperature=0.4,
        )
        logger.info(
            "weekly_insight.generated",
            account_id=account_context.get("account_id"),
            insight_len=len(insight),
        )
        return insight.strip()
