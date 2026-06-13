"""Builders that wire CIE use cases to concrete adapters from settings.

Keeps adapter construction in one place so the API routers and Celery tasks build
the same objects the same way.
"""

from __future__ import annotations

from typing import Any

from redis import Redis

from adcopilot.config import Settings
from adcopilot.infrastructure.adapters.claude_generation_adapter import ClaudeKeywordGenerator
from adcopilot.infrastructure.adapters.dataforseo_adapter import DataForSeoAdapter
from adcopilot.infrastructure.cache.keyword_volume_cache import KeywordVolumeCache
from adcopilot.infrastructure.google_ads.keyword_volume_planner_adapter import (
    GoogleKeywordPlannerVolumeAdapter,
)
from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
from adcopilot.infrastructure.llm.fake_client import FakeLLMClient


def build_llm(settings: Settings) -> Any:
    """Return an LLM client. Falls back to a fake when no API key is set so the
    engine never hard-crashes in a misconfigured/dev environment."""
    if settings.LLM_API_KEY:
        return AnthropicClient(api_key=settings.LLM_API_KEY, model=settings.LLM_MODEL_DEFAULT)
    return FakeLLMClient(default="[]")


def build_redis(settings: Settings) -> Redis:  # type: ignore[type-arg]
    return Redis.from_url(settings.REDIS_URL)


def build_volume_cache(settings: Settings, redis: Any | None = None) -> KeywordVolumeCache:
    return KeywordVolumeCache(
        redis or build_redis(settings), ttl_seconds=settings.KEYWORD_VOLUME_CACHE_TTL_SECONDS
    )


def build_keyword_generator(settings: Settings, prompt_repo: Any | None = None) -> Any:
    return ClaudeKeywordGenerator(build_llm(settings), prompt_repo=prompt_repo)


def build_kp_volume_adapter(settings: Settings) -> GoogleKeywordPlannerVolumeAdapter:
    return GoogleKeywordPlannerVolumeAdapter(settings)


def build_dataforseo_adapter(settings: Settings) -> DataForSeoAdapter:
    return DataForSeoAdapter(settings)


def build_hook_generator(settings: Settings, prompt_repo: Any | None = None) -> Any:
    from adcopilot.infrastructure.adapters.claude_hook_adapter import ClaudeHookGenerator

    return ClaudeHookGenerator(build_llm(settings), prompt_repo=prompt_repo)


def build_hook_judge(settings: Settings, prompt_repo: Any | None = None) -> Any:
    """The judge is the highest-leverage critic pass and runs on ~14 candidates,
    so it uses the premium model when one is configured (negligible cost)."""
    from adcopilot.infrastructure.adapters.claude_hook_adapter import ClaudeHookJudge

    llm: Any
    if settings.LLM_API_KEY:
        llm = AnthropicClient(api_key=settings.LLM_API_KEY, model=settings.LLM_MODEL_PREMIUM)
    else:
        llm = FakeLLMClient(default="[]")
    return ClaudeHookJudge(llm, prompt_repo=prompt_repo)
