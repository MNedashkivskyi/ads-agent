"""Helpers for coaxing strict JSON out of LLM completions.

LLMs sometimes wrap JSON in ```json fences or add a stray sentence. These helpers
strip the common decorations and parse, raising a typed ``LLMError`` on failure so
callers can implement a retry-once-then-fail policy.
"""

from __future__ import annotations

import json
import re
from typing import Any

from adcopilot.domain.exceptions import LLMError

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def strip_fences(text: str) -> str:
    """Remove a leading/trailing markdown code fence if present."""
    stripped = text.strip()
    stripped = _FENCE_RE.sub("", stripped)
    return stripped.strip()


def _slice_to_outer(text: str, open_ch: str, close_ch: str) -> str | None:
    start = text.find(open_ch)
    end = text.rfind(close_ch)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + 1]


def parse_json_array(raw: str) -> list[Any]:
    """Parse a JSON array from an LLM completion, tolerating fences/prose."""
    candidate = strip_fences(raw)
    for attempt in (candidate, _slice_to_outer(candidate, "[", "]")):
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return parsed
        raise LLMError("Expected a JSON array from the LLM")
    raise LLMError("LLM did not return valid JSON array")


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM completion, tolerating fences/prose."""
    candidate = strip_fences(raw)
    for attempt in (candidate, _slice_to_outer(candidate, "{", "}")):
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
        raise LLMError("Expected a JSON object from the LLM")
    raise LLMError("LLM did not return valid JSON object")
