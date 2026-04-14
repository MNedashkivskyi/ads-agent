"""Celery-side Sentry wiring — context reset + task tagging.

``sentry_sdk.integrations.celery.CeleryIntegration`` already captures
unhandled task exceptions and creates a performance transaction per task,
but it doesn't know about AdCopilot's per-user / per-account context vars.
These signal handlers reset the context at the start of each task and
propagate the task name onto every event.
"""

from __future__ import annotations

import structlog
from celery.signals import (
    task_failure,
    task_postrun,
    task_prerun,
    worker_process_init,
)

from adcopilot.observability.sentry import clear_context, init_sentry

logger = structlog.get_logger(__name__)


@worker_process_init.connect  # type: ignore[untyped-decorator]
def _init_worker_sentry(**_: object) -> None:
    """Initialise Sentry once per worker process.

    Celery forks worker processes after importing this module, so calling
    ``init_sentry`` at import time would leave the forks without a live SDK.
    """
    init_sentry(component="celery-worker")


@task_prerun.connect  # type: ignore[untyped-decorator]
def _reset_context_on_prerun(
    task_id: str | None = None, task: object | None = None, **_: object
) -> None:
    """Reset request-scoped context at the start of every task.

    Celery reuses worker processes, so leftover context from a prior task
    would contaminate subsequent events.
    """
    clear_context()
    try:
        import sentry_sdk

        task_name = getattr(task, "name", None)
        if task_name:
            sentry_sdk.set_tag("celery.task", task_name)
        if task_id:
            sentry_sdk.set_tag("celery.task_id", task_id)
    except Exception:
        # Observability must never break the task.
        logger.exception("failed to tag celery task in sentry")


@task_postrun.connect  # type: ignore[untyped-decorator]
def _clear_context_on_postrun(**_: object) -> None:
    """Clear context after each task so leaks can't outlive the task."""
    clear_context()


@task_failure.connect  # type: ignore[untyped-decorator]
def _capture_failure(
    sender: object | None = None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    **_: object,
) -> None:
    """Log task failures with structlog — Sentry capture is done by the
    ``CeleryIntegration`` itself.  This handler exists so that test/dev
    setups without a Sentry DSN still get a clear failure signal."""
    task_name = getattr(sender, "name", None)
    logger.error(
        "celery task failed",
        task=task_name,
        task_id=task_id,
        error=str(exception) if exception else None,
    )
