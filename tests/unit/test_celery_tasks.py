"""Unit tests for Celery task logic: Redis lock and manual trigger endpoint."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Redis lock tests
# ---------------------------------------------------------------------------


def test_snapshot_task_skips_when_lock_held() -> None:
    """If the Redis lock is already held, the task logs a warning and returns skipped=True."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = None  # lock not acquired

    with patch(
        "adcopilot.interfaces.worker.tasks._redis_client",
        return_value=mock_redis,
    ):
        from adcopilot.interfaces.worker.tasks import snapshot_account_task

        # Call the underlying function directly (bypass Celery)
        result = snapshot_account_task.__wrapped__(
            "account-id-123",
            "2026-01-15",
        )

    assert result == {"skipped": True}
    mock_redis.set.assert_called_once_with(
        "lock:snapshot:account-id-123:2026-01-15",
        "1",
        nx=True,
        ex=7200,
    )


def test_snapshot_task_releases_lock_on_success() -> None:
    """Lock must be deleted after a successful run."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True  # lock acquired

    fake_result = MagicMock()
    fake_result.campaigns = 3
    fake_result.ad_groups = 5
    fake_result.keywords = 10
    fake_result.search_terms = 20
    fake_result.ads = 4
    fake_result.duration_seconds = 1.23
    fake_result.success = True

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._redis_client",
            return_value=mock_redis,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._run_snapshot",
            new=AsyncMock(return_value=fake_result),
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._run_detection",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._record_qs_history",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "adcopilot.interfaces.worker.tasks.snapshot_ga4_data_task",
        ) as mock_ga4_task,
        patch(
            "adcopilot.interfaces.worker.tasks.snapshot_auction_insights_task",
        ) as mock_auction_task,
    ):
        mock_ga4_task.delay = MagicMock()
        mock_auction_task.delay = MagicMock()

        from adcopilot.interfaces.worker.tasks import snapshot_account_task

        result = snapshot_account_task.__wrapped__(
            "account-id-123",
            "2026-01-15",
        )

    assert result["success"] is True
    assert result["campaigns"] == 3
    mock_redis.delete.assert_called_once_with("lock:snapshot:account-id-123:2026-01-15")


def test_snapshot_task_releases_lock_on_exception() -> None:
    """Lock must be deleted even if an exception is raised (finally block)."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    with (
        patch(
            "adcopilot.interfaces.worker.tasks._redis_client",
            return_value=mock_redis,
        ),
        patch(
            "adcopilot.interfaces.worker.tasks._run_snapshot",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(RuntimeError, match="boom"),
    ):
        from adcopilot.interfaces.worker.tasks import snapshot_account_task

        snapshot_account_task.__wrapped__(
            "account-id-123",
            "2026-01-15",
        )

    mock_redis.delete.assert_called_once_with("lock:snapshot:account-id-123:2026-01-15")


# ---------------------------------------------------------------------------
# Manual trigger endpoint tests
# ---------------------------------------------------------------------------


def test_trigger_snapshot_returns_202() -> None:
    """POST /api/accounts/{id}/snapshots should enqueue and return 202."""
    mock_task = MagicMock()
    mock_task.id = "celery-task-uuid-123"

    with patch("adcopilot.interfaces.api.snapshots.snapshot_account_task") as mock_celery_task:
        mock_celery_task.delay.return_value = mock_task

        from adcopilot.main import create_app

        app = create_app()
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.post(
                "/api/accounts/my-account-id/snapshots",
                json={"date": "2026-01-15"},
            )

    assert resp.status_code == 202
    data = resp.json()
    assert data["task_id"] == "celery-task-uuid-123"
    assert data["account_id"] == "my-account-id"
    assert data["snapshot_date"] == "2026-01-15"
    mock_celery_task.delay.assert_called_once_with("my-account-id", "2026-01-15")


def test_trigger_snapshot_defaults_to_today() -> None:
    """When no date body is given, it defaults to today."""
    mock_task = MagicMock()
    mock_task.id = "task-abc"

    with patch("adcopilot.interfaces.api.snapshots.snapshot_account_task") as mock_celery_task:
        mock_celery_task.delay.return_value = mock_task

        from adcopilot.main import create_app

        app = create_app()
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.post("/api/accounts/acc-1/snapshots")

    assert resp.status_code == 202
    data = resp.json()
    assert data["snapshot_date"] == date.today().isoformat()
