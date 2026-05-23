"""Unit tests for weekly insight use case and Celery task (Task 5.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_generate_weekly_insight_returns_text() -> None:
    from adcopilot.application.use_cases.generate_weekly_insight import GenerateWeeklyInsightUseCase

    llm = AsyncMock()
    llm.complete.return_value = "  W tym tygodniu budżet kampanii 'Sklep' był wykorzystany w 95%.  "

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "Dane: {account_context}"
    prompt_repo.get_latest.return_value = pv

    use_case = GenerateWeeklyInsightUseCase(llm=llm, prompt_repo=prompt_repo)
    result = await use_case.execute({"account_id": "acc-1", "summary": {"total_spend_pln": 500}})

    assert "budżet" in result
    assert not result.startswith(" ")  # stripped


@pytest.mark.asyncio
async def test_generate_weekly_insight_calls_llm_once() -> None:
    from adcopilot.application.use_cases.generate_weekly_insight import GenerateWeeklyInsightUseCase

    llm = AsyncMock()
    llm.complete.return_value = "Insight tekst."

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "{account_context}"
    prompt_repo.get_latest.return_value = pv

    use_case = GenerateWeeklyInsightUseCase(llm=llm, prompt_repo=prompt_repo)
    await use_case.execute({"account_id": "acc-1"})

    llm.complete.assert_called_once()


def test_task_is_registered() -> None:
    import adcopilot.interfaces.worker.tasks  # noqa: F401
    from adcopilot.interfaces.worker.celery_app import celery_app

    assert "adcopilot.interfaces.worker.tasks.generate_weekly_insight_task" in celery_app.tasks


def test_beat_schedule_includes_weekly_insight() -> None:
    from adcopilot.interfaces.worker.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "weekly-proactive-insights" in beat
    entry = beat["weekly-proactive-insights"]
    assert entry["task"] == "adcopilot.interfaces.worker.tasks.generate_weekly_insight_task"


def test_send_insight_method_exists_on_notifier() -> None:
    from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

    assert hasattr(SqlWebNotifier, "send_insight")
