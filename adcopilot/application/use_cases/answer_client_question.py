"""AnswerClientQuestionUseCase — LLM Q&A grounded on account context."""

from __future__ import annotations

import json
from typing import Any

import structlog

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "client_qa_v1"
_SYSTEM = (
    "Jesteś ekspertem Google Ads pomagającym polskim właścicielom firm MŚP. "
    "Odpowiadaj wyłącznie po polsku. Cytuj tylko liczby z dostarczonych danych."
)


class AnswerClientQuestionUseCase:
    def __init__(self, llm: LLMClient, prompt_repo: PromptVersionRepository) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def execute(
        self,
        question: str,
        account_context: dict[str, Any],
    ) -> str:
        """Return a Polish answer grounded on the provided account context."""
        context_json = json.dumps(account_context, ensure_ascii=False, indent=2)
        prompt_template = await get_latest_prompt(self._prompt_repo, _PROMPT_KEY)
        user_msg = prompt_template.format(
            account_context=context_json,
            question=question,
        )
        answer = await self._llm.complete(
            system=_SYSTEM,
            user=user_msg,
            max_tokens=600,
            temperature=0.2,
        )
        logger.info(
            "client_qa.answered",
            account_id=account_context.get("account_id"),
            question_len=len(question),
            answer_len=len(answer),
        )
        return answer.strip()
