"""Claude-backed hook generator + judge (implements HookGeneratorPort/HookJudgePort).

Both retry exactly once on malformed JSON, then raise a clean ``LLMError``. The
generator drops hooks that violate their surface's char limit or carry an unknown
angle/surface (defence in depth — the entity also enforces limits).
"""

from __future__ import annotations

import json

import structlog

from adcopilot.application.ports.hook_generator import GeneratedHook, JudgeResult
from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.domain.campaign_intelligence.creatives.ad_surface import AdSurface, within_limit
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.exceptions import LLMError
from adcopilot.infrastructure.llm import json_parsing
from adcopilot.infrastructure.prompts import hook_generation, hook_judge

logger = structlog.get_logger(__name__)

_VALID_ANGLES = {a.value for a in Angle}
_VALID_SURFACES = {s.value for s in AdSurface}
_MAX_TOKENS = 2000


async def _load_templates(
    prompt_repo: PromptVersionRepository | None, key: str
) -> tuple[str | None, str | None]:
    if prompt_repo is None:
        return None, None
    try:
        pv = await prompt_repo.get_latest(key)
    except Exception:  # noqa: BLE001
        return None, None
    if pv is None:
        return None, None
    try:
        data = json.loads(pv.content)
        return data.get("system"), data.get("user_template")
    except (json.JSONDecodeError, AttributeError):
        return None, None


class ClaudeHookGenerator:
    def __init__(
        self, llm: LLMClient, prompt_repo: PromptVersionRepository | None = None
    ) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        angle_allocation: dict[str, int],
        surfaces: list[str],
        language: str = "pl",
        focus: str | None = None,
    ) -> list[GeneratedHook]:
        system_tmpl, user_tmpl = await _load_templates(
            self._prompt_repo, hook_generation.HOOK_GENERATION_PROMPT_KEY
        )
        system, user = hook_generation.render(
            service=service,
            vertical=vertical,
            problems=problems,
            angle_allocation=angle_allocation,
            surfaces=surfaces,
            language=language,
            focus=focus,
            system_template=system_tmpl,
            user_template=user_tmpl,
        )
        last: Exception | None = None
        for attempt in range(2):
            raw = await self._llm.complete(
                system=system, user=user, max_tokens=_MAX_TOKENS, temperature=0.7
            )
            try:
                return self._parse(raw)
            except LLMError as exc:
                last = exc
                logger.warning("hook_generation.malformed", attempt=attempt + 1, error=str(exc))
        raise LLMError(f"Hook generation malformed JSON after retry: {last}")

    @staticmethod
    def _parse(raw: str) -> list[GeneratedHook]:
        items = json_parsing.parse_json_array(raw)
        out: list[GeneratedHook] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            angle = str(item.get("angle", "")).strip().upper()
            surface = str(item.get("surface", "")).strip().upper()
            if not text or angle not in _VALID_ANGLES or surface not in _VALID_SURFACES:
                continue
            if not within_limit(AdSurface(surface), text):
                continue  # drop over-limit hooks (entity would reject them anyway)
            out.append(GeneratedHook(text=text, angle=angle, surface=surface))
        if not out:
            raise LLMError("No valid hooks parsed from LLM output")
        return out


class ClaudeHookJudge:
    def __init__(
        self, llm: LLMClient, prompt_repo: PromptVersionRepository | None = None
    ) -> None:
        self._llm = llm
        self._prompt_repo = prompt_repo

    async def judge(
        self,
        hooks: list[GeneratedHook],
        *,
        service: str,
        vertical: str,
        language: str = "pl",
    ) -> list[JudgeResult]:
        if not hooks:
            return []
        system_tmpl, user_tmpl = await _load_templates(
            self._prompt_repo, hook_judge.HOOK_JUDGE_PROMPT_KEY
        )
        system, user = hook_judge.render(
            hooks=[h.text for h in hooks],
            service=service,
            vertical=vertical,
            system_template=system_tmpl,
            user_template=user_tmpl,
        )
        last: Exception | None = None
        for attempt in range(2):
            raw = await self._llm.complete(
                system=system, user=user, max_tokens=_MAX_TOKENS, temperature=0.2
            )
            try:
                return self._parse(raw)
            except LLMError as exc:
                last = exc
                logger.warning("hook_judge.malformed", attempt=attempt + 1, error=str(exc))
        raise LLMError(f"Hook judge malformed JSON after retry: {last}")

    @staticmethod
    def _parse(raw: str) -> list[JudgeResult]:
        items = json_parsing.parse_json_array(raw)
        out: list[JudgeResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            out.append(
                JudgeResult(
                    text=text,
                    specificity=_clamp(item.get("specificity")),
                    tension=_clamp(item.get("tension")),
                    pain_truth=_clamp(item.get("pain_truth")),
                    clarity=_clamp(item.get("clarity")),
                )
            )
        if not out:
            raise LLMError("No valid judge results parsed from LLM output")
        return out


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
