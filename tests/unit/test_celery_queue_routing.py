"""Guard: worker tasks land on the queue the Railway worker actually consumes.

Regression test for the free-audit scan (and CIE tasks) hanging forever: their
modules matched no `task_routes` entry and `task_default_queue` was unset, so they
fell back to Celery's implicit "celery" queue while the worker only drained
`-Q default`. Every task must default to "default".
"""

from __future__ import annotations

from adcopilot.interfaces.worker.celery_app import celery_app


def test_default_queue_is_the_one_the_worker_consumes() -> None:
    assert celery_app.conf.task_default_queue == "default"


def test_worker_includes_the_audit_task_module() -> None:
    # The worker loads tasks from the `include` list; audit_tasks must be there
    # so the scan + settle tasks are registered when the worker boots.
    assert "adcopilot.interfaces.worker.audit_tasks" in (celery_app.conf.include or [])


def test_audit_tasks_register_on_the_app_once_imported() -> None:
    import adcopilot.interfaces.worker.audit_tasks  # noqa: F401 — registers @celery_app.task

    for name in (
        "adcopilot.interfaces.worker.audit_tasks.run_audit_scan_task",
        "adcopilot.interfaces.worker.audit_tasks.settle_recovery_ledger_task",
    ):
        assert name in celery_app.tasks
