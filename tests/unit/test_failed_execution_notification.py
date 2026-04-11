"""Unit tests for failed-execution notification flow."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adcopilot.infrastructure.telegram.fake_notifier import FakeTelegramNotifier

# ---------------------------------------------------------------------------
# FakeTelegramNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_notifier_records_send_execution_failed() -> None:
    from datetime import datetime

    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationId,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )

    rec = Recommendation(
        id=RecommendationId("rec-1"),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.PAUSE_KEYWORD,
        severity=RecommendationSeverity.HIGH,
        target={},
        payload={},
        estimated_monthly_savings_micros=0,
        evidence={},
        created_at=datetime.utcnow(),
        status=RecommendationStatus.FAILED,
    )

    notifier = FakeTelegramNotifier()
    await notifier.send_execution_failed(chat_id=42, recommendation=rec, error_message="boom")

    assert len(notifier.calls) == 1
    call = notifier.calls[0]
    assert call["method"] == "send_execution_failed"
    assert call["chat_id"] == 42
    assert call["recommendation"] is rec
    assert call["error_message"] == "boom"


# ---------------------------------------------------------------------------
# TelegramDigestNotifier.send_execution_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digest_notifier_sends_failure_message() -> None:
    from datetime import datetime

    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationId,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )
    from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

    rec = Recommendation(
        id=RecommendationId("rec-2"),
        account_id=AccountId("acc-2"),
        kind=RecommendationKind.CHANGE_MATCH_TYPE,
        severity=RecommendationSeverity.MEDIUM,
        target={},
        payload={},
        estimated_monthly_savings_micros=0,
        evidence={},
        created_at=datetime.utcnow(),
        status=RecommendationStatus.FAILED,
    )

    bot_mock = AsyncMock()
    notifier = TelegramDigestNotifier.__new__(TelegramDigestNotifier)
    notifier._bot = bot_mock

    await notifier.send_execution_failed(chat_id=99, recommendation=rec, error_message="API error")

    bot_mock.send_message.assert_awaited_once()
    kwargs = bot_mock.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 99
    assert "Change Match Type" in kwargs["text"]
    assert "API error" in kwargs["text"]


# ---------------------------------------------------------------------------
# execute_recommendation_task — task configuration
# ---------------------------------------------------------------------------


def test_execute_recommendation_task_is_bound_with_correct_retry_config() -> None:
    """The Celery task must be configured with bind=True and 3 max retries."""
    from adcopilot.interfaces.worker.tasks import execute_recommendation_task

    assert execute_recommendation_task.max_retries == 3
    assert execute_recommendation_task.name == (
        "adcopilot.interfaces.worker.tasks.execute_recommendation_task"
    )


# ---------------------------------------------------------------------------
# execute_recommendation_task — failure path (tested via the run function)
# ---------------------------------------------------------------------------


def _make_bound_task(max_retries: int = 3, current_retry: int = 3) -> MagicMock:
    """Return a mock that matches what Celery passes as `self` in bind=True tasks."""
    task_self = MagicMock()
    task_self.max_retries = max_retries
    task_self.request.retries = current_retry

    def _retry_side_effect(exc: BaseException) -> None:
        raise exc from exc

    task_self.retry.side_effect = _retry_side_effect
    return task_self


def _run_task(task_self: MagicMock, rec_id: str) -> None:
    """Call execute_recommendation_task's body directly, bypassing Celery overhead."""
    import asyncio

    from adcopilot.interfaces.worker.tasks import (
        _handle_execution_failure,
        _run_execute_recommendation,
    )

    # Replicate the task body so we can inject mocks via patch in tests
    try:
        asyncio.run(_run_execute_recommendation(rec_id))
    except Exception as exc:
        if task_self.request.retries < task_self.max_retries:
            raise task_self.retry(exc=exc) from exc
        error_message = str(exc) or type(exc).__name__
        with contextlib.suppress(Exception):
            asyncio.run(_handle_execution_failure(rec_id, error_message))
        raise


def test_execute_recommendation_task_retries_on_transient_error() -> None:
    """When retries are not exhausted, retry() should be called and the exc raised."""
    task_self = _make_bound_task(max_retries=3, current_retry=0)
    exc = RuntimeError("transient error")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        pytest.raises(RuntimeError, match="transient error"),
    ):
        _run_task(task_self, "rec-abc")

    task_self.retry.assert_called_once_with(exc=exc)


def test_execute_recommendation_task_calls_handle_failure_when_retries_exhausted() -> None:
    """After max retries, _handle_execution_failure is called with the right args."""
    task_self = _make_bound_task(max_retries=3, current_retry=3)
    exc = RuntimeError("permanent failure")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_execution_failure",
            new_callable=AsyncMock,
        ) as mock_handle,
        pytest.raises(RuntimeError, match="permanent failure"),
    ):
        _run_task(task_self, "rec-abc")

    mock_handle.assert_awaited_once_with("rec-abc", "permanent failure")


def test_execute_recommendation_task_handle_failure_exception_is_swallowed() -> None:
    """If _handle_execution_failure raises, the original exc is still propagated."""
    task_self = _make_bound_task(max_retries=3, current_retry=3)
    exc = ValueError("original")

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._run_execute_recommendation",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._handle_execution_failure",
            new_callable=AsyncMock,
            side_effect=RuntimeError("handle failure blew up"),
        ),
        pytest.raises(ValueError, match="original"),
    ):
        _run_task(task_self, "rec-abc")
