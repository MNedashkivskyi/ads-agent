"""Unit tests for monthly_landing_page_audit_task."""

from __future__ import annotations

import pytest


def test_task_is_registered() -> None:
    import adcopilot.interfaces.worker.tasks  # noqa: F401 — ensures tasks are registered
    from adcopilot.interfaces.worker.celery_app import celery_app

    registered = celery_app.tasks.keys()
    assert "adcopilot.interfaces.worker.tasks.monthly_landing_page_audit_task" in registered


def test_beat_schedule_includes_monthly_audit() -> None:
    from adcopilot.interfaces.worker.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "monthly-landing-page-audit" in beat
    entry = beat["monthly-landing-page-audit"]
    assert entry["task"] == "adcopilot.interfaces.worker.tasks.monthly_landing_page_audit_task"


def test_task_function_exists() -> None:
    from adcopilot.interfaces.worker import tasks

    assert hasattr(tasks, "monthly_landing_page_audit_task")
    assert callable(tasks.monthly_landing_page_audit_task)
