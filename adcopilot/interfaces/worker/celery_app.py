"""Celery application factory."""

from celery import Celery
from celery.schedules import crontab

from adcopilot.config import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()

    app = Celery("adcopilot")
    app.config_from_object(
        {
            "broker_url": settings.REDIS_URL,
            "result_backend": settings.REDIS_URL,
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "beat_schedule": {
                "nightly-snapshots": {
                    "task": "adcopilot.interfaces.worker.tasks.run_nightly_snapshots",
                    "schedule": crontab(hour=3, minute=0),
                },
                "daily-digests": {
                    "task": "adcopilot.interfaces.worker.tasks.send_daily_digests_task",
                    "schedule": crontab(hour=9, minute=0),
                },
            },
            "task_routes": {
                "adcopilot.interfaces.worker.tasks.*": {"queue": "default"},
            },
        }
    )
    return app


celery_app = create_celery_app()
