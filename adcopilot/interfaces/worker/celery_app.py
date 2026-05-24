"""Celery application factory."""

from celery import Celery
from celery.schedules import crontab

from adcopilot.config import get_settings

# Importing the signals module connects the Celery signal handlers at import
# time.  These handlers reset the per-request context on task_prerun and
# re-initialise Sentry inside each forked worker process.
from adcopilot.observability import celery_sentry, init_sentry  # noqa: F401


def create_celery_app() -> Celery:
    settings = get_settings()

    # Initialise Sentry for beat/embedded contexts.  Fork worker processes
    # re-init via the worker_process_init signal (see celery_sentry.py).
    init_sentry(component="celery-app")

    app = Celery("adcopilot")
    app.config_from_object(
        {
            # Explicitly register the tasks module so the worker process
            # can find task functions.  Without this, task.delay() from
            # the API enqueues by string name, but the worker rejects
            # with "Received unregistered task".
            "include": ["adcopilot.interfaces.worker.tasks"],
            "broker_url": settings.REDIS_URL,
            "result_backend": settings.REDIS_URL,
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
            "timezone": "UTC",
            "enable_utc": True,
            "beat_schedule": {
                "nightly-db-backup": {
                    # 2:00 AM UTC — runs before snapshot ingestion so the
                    # backup always captures the previous day's committed data.
                    "task": "adcopilot.interfaces.worker.tasks.nightly_db_backup_task",
                    "schedule": crontab(hour=2, minute=0),
                },
                "nightly-snapshots": {
                    "task": "adcopilot.interfaces.worker.tasks.run_nightly_snapshots",
                    "schedule": crontab(hour=3, minute=0),
                },
                "daily-digests": {
                    "task": "adcopilot.interfaces.worker.tasks.send_daily_digests_task",
                    "schedule": crontab(hour=9, minute=0),
                },
                "trial-reminders": {
                    "task": "adcopilot.interfaces.worker.tasks.send_trial_reminders_task",
                    "schedule": crontab(hour=10, minute=0),
                },
                "hourly-anomaly-detection": {
                    # Runs at :05 past every hour so fresh data is available
                    # from the Google Ads API before the check executes.
                    "task": "adcopilot.interfaces.worker.tasks.run_anomaly_detection_task",
                    "schedule": crontab(minute=5),
                },
                "weekly-bidding-check": {
                    # Monday 4:00 AM UTC — after the nightly snapshot so the
                    # latest 30-day conversion data is available.
                    "task": "adcopilot.interfaces.worker.tasks.check_bidding_upgrade_task",
                    "schedule": crontab(hour=4, minute=0, day_of_week="monday"),
                },
                "weekly-rlsa-check": {
                    # Tuesday 5:00 AM UTC — check RLSA eligibility for GROWTH accounts.
                    "task": "adcopilot.interfaces.worker.tasks.check_rlsa_eligibility_task",
                    "schedule": crontab(hour=5, minute=0, day_of_week="tuesday"),
                },
                "monthly-remarketing-campaign-check": {
                    # 1st of month 6:00 AM UTC — propose remarketing campaigns for eligible accounts.
                    "task": "adcopilot.interfaces.worker.tasks.check_remarketing_campaign_eligibility_task",
                    "schedule": crontab(hour=6, minute=0, day_of_month="1"),
                },
                "daily-performance-comparisons": {
                    # 6:00 AM UTC daily — after nightly snapshot so current metrics are fresh.
                    "task": "adcopilot.interfaces.worker.tasks.compare_recommendation_performance_task",
                    "schedule": crontab(hour=6, minute=0),
                },
                "weekly-performance-reports": {
                    # Fridays 10:00 AM UTC — weekly impact summary to users with Telegram linked.
                    "task": "adcopilot.interfaces.worker.tasks.send_weekly_performance_report_task",
                    "schedule": crontab(hour=10, minute=0, day_of_week="friday"),
                },
                "weekly-benchmark-aggregation": {
                    # Wednesday 5:00 AM UTC — after Tuesday snapshots settle.
                    "task": "adcopilot.interfaces.worker.tasks.aggregate_benchmarks_task",
                    "schedule": crontab(hour=5, minute=0, day_of_week="wednesday"),
                },
                "monthly-landing-page-audit": {
                    # 2nd of month 7:00 AM UTC — score all active landing pages.
                    "task": "adcopilot.interfaces.worker.tasks.monthly_landing_page_audit_task",
                    "schedule": crontab(hour=7, minute=0, day_of_month="2"),
                },
                "weekly-proactive-insights": {
                    # Mondays 8:30 AM UTC — generate strategic weekly insight per user.
                    "task": "adcopilot.interfaces.worker.tasks.generate_weekly_insight_task",
                    "schedule": crontab(hour=8, minute=30, day_of_week="monday"),
                },
                "weekly-qs-improvement-check": {
                    # Wednesday 5:00 AM UTC — auto-create plans for low-QS keywords,
                    # evaluate plans past their measurement window, and digest results.
                    "task": "adcopilot.interfaces.worker.tasks.weekly_qs_improvement_check_task",
                    "schedule": crontab(hour=5, minute=0, day_of_week=3),
                },
                "monthly-performance-reports": {
                    # 1st of month 8:00 AM UTC — generate PDF performance reports for all active accounts.
                    "task": "adcopilot.interfaces.worker.tasks.monthly_performance_reports_task",
                    "schedule": crontab(hour=8, minute=0, day_of_month="1"),
                },
            },
            "task_routes": {
                "adcopilot.interfaces.worker.tasks.*": {"queue": "default"},
            },
        }
    )
    return app


celery_app = create_celery_app()
