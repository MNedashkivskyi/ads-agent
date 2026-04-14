"""Sentry initialisation, PII scrubbing, and request-scoped context propagation.

Sentry is wired into three entry points:

* **FastAPI** — via ``sentry_sdk.integrations.fastapi.FastApiIntegration`` and
  ``StarletteIntegration`` (added automatically when ``init_sentry`` is called
  before ``create_app``).  A middleware (:class:`SentryContextMiddleware`)
  augments each request with ``user_id`` / ``account_id`` tags whenever the
  caller supplies them via the :func:`set_user_context` /
  :func:`set_account_context` helpers.
* **Celery workers** — via ``sentry_sdk.integrations.celery.CeleryIntegration``.
  Celery signals (:mod:`adcopilot.observability.celery_sentry`) clear the
  request-scoped contextvars on ``task_prerun`` and tag each task span with the
  task name.
* **Background scripts** (``scripts/run_bot.py`` etc.) — initialise Sentry
  directly via :func:`init_sentry`.

All three share the same :func:`_before_send` hook which scrubs known PII
(refresh tokens, emails, Google Ads customer IDs) from outbound events.
"""

from __future__ import annotations

import os
import re
import subprocess
from contextvars import ContextVar
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Request-scoped context (mirrored into every Sentry event)
# ---------------------------------------------------------------------------

_user_id_ctx: ContextVar[str | None] = ContextVar("sentry_user_id", default=None)
_account_id_ctx: ContextVar[str | None] = ContextVar("sentry_account_id", default=None)


def set_user_context(user_id: str | None) -> None:
    """Tag the current request / task with ``user_id``.

    The value is propagated into every Sentry event emitted from this
    context via :func:`_before_send`.  ``user_id`` is an opaque UUID, not
    PII, so it is safe to send to Sentry.
    """
    _user_id_ctx.set(user_id)
    if user_id is not None:
        import sentry_sdk

        sentry_sdk.set_tag("user_id", user_id)
        sentry_sdk.set_user({"id": user_id})


def set_account_context(account_id: str | None) -> None:
    """Tag the current request / task with ``account_id`` (AdCopilot UUID).

    The AdCopilot ``account_id`` is an internal UUID — distinct from the
    Google Ads ``customer_id`` which IS PII and must never be sent.
    """
    _account_id_ctx.set(account_id)
    if account_id is not None:
        import sentry_sdk

        sentry_sdk.set_tag("account_id", account_id)


def clear_context() -> None:
    """Reset request-scoped context.  Call at the start of each request/task."""
    _user_id_ctx.set(None)
    _account_id_ctx.set(None)


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

# Google Ads customer IDs look like 'customers/1234567890' or just '1234567890'
# when they appear as a 10-digit number.  We redact both shapes.
_CUSTOMER_ID_RE = re.compile(r"\bcustomers/\d{8,12}\b")
_BARE_CUSTOMER_ID_RE = re.compile(r"(?<!\d)\d{10}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Google OAuth refresh tokens are typically 'ya29.<opaque>' or '1//<opaque>'.
_TOKEN_RE = re.compile(r"\b(?:ya29\.[\w.-]+|1//[\w.-]+)")

_PII_KEYS: frozenset[str] = frozenset(
    {
        "refresh_token",
        "access_token",
        "token",
        "password",
        "password_hash",
        "secret",
        "api_key",
        "authorization",
        "cookie",
        "set-cookie",
        "email",
        "customer_id",
        "login_customer_id",
    }
)

_REDACTED = "[REDACTED]"


def _scrub_str(value: str) -> str:
    """Best-effort scrub of sensitive patterns in a free-form string."""
    value = _TOKEN_RE.sub(_REDACTED, value)
    value = _EMAIL_RE.sub(_REDACTED, value)
    value = _CUSTOMER_ID_RE.sub(_REDACTED, value)
    value = _BARE_CUSTOMER_ID_RE.sub(_REDACTED, value)
    return value


def _scrub(obj: Any, depth: int = 0) -> Any:
    """Recursively scrub PII from ``obj`` in place-ish.

    The recursion depth is capped (Sentry events can be deeply nested) — after
    the limit strings and dicts are passed through untouched, which is a
    deliberate trade-off between thoroughness and CPU.
    """
    if depth > 6:
        return obj
    if isinstance(obj, dict):
        scrubbed: dict[Any, Any] = {}
        for k, v in obj.items():
            key_lower = str(k).lower() if k is not None else ""
            if key_lower in _PII_KEYS:
                scrubbed[k] = _REDACTED
            else:
                scrubbed[k] = _scrub(v, depth + 1)
        return scrubbed
    if isinstance(obj, list):
        return [_scrub(v, depth + 1) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_scrub(v, depth + 1) for v in obj)
    if isinstance(obj, str):
        return _scrub_str(obj)
    return obj


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Sentry ``before_send`` hook — attaches context tags and scrubs PII.

    Runs on every event just before it is serialised for transport, so both
    auto-captured events (unhandled exceptions, logs) and manual
    ``capture_exception`` / ``capture_message`` calls pass through here.
    """
    # 1. Tag with request-scoped identifiers.  Do this before scrubbing so the
    #    IDs survive (they are not PII — they're internal UUIDs).
    uid = _user_id_ctx.get()
    aid = _account_id_ctx.get()
    if uid is not None:
        event.setdefault("tags", {}).setdefault("user_id", uid)
        event.setdefault("user", {}).setdefault("id", uid)
    if aid is not None:
        event.setdefault("tags", {}).setdefault("account_id", aid)

    # 2. Scrub common PII locations.  ``user.email`` is always removed even if
    #    some upstream sentry_sdk integration populates it.
    user = event.get("user") or {}
    if isinstance(user, dict):
        user.pop("email", None)
        user.pop("username", None)
        user.pop("ip_address", None)
    event["user"] = user

    # 3. Scrub everywhere else recursively — request body, extras, contexts,
    #    breadcrumbs, exception values.
    for key in ("extra", "contexts", "request", "breadcrumbs", "exception"):
        if key in event:
            event[key] = _scrub(event[key])

    # 4. Scrub the top-level ``logentry.message`` and ``message`` fields.
    if isinstance(event.get("message"), str):
        event["message"] = _scrub_str(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict) and isinstance(logentry.get("message"), str):
        logentry["message"] = _scrub_str(logentry["message"])

    return event


def _before_send_transaction(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the same scrubbing/tagging to performance transactions."""
    return _before_send(event, hint)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def _resolve_release() -> str | None:
    """Resolve the release version.

    Preference order:

    1. ``SENTRY_RELEASE`` env var (set by the build pipeline).
    2. ``RAILWAY_GIT_COMMIT_SHA`` — injected by Railway builds.
    3. ``GIT_SHA`` — fallback for other platforms.
    4. ``git rev-parse --short HEAD`` — local dev convenience.
    """
    for key in ("SENTRY_RELEASE", "RAILWAY_GIT_COMMIT_SHA", "GIT_SHA"):
        value = os.environ.get(key)
        if value:
            return value
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


_ALLOWED_ENVIRONMENTS = frozenset({"local", "staging", "production"})


def _resolve_environment(app_env: str) -> str:
    """Map the AdCopilot ``ENV`` value onto a canonical Sentry environment.

    The task specifies three names: ``local``, ``staging``, ``production``.
    Anything else (``dev``, ``test``, ``ci``) is folded into ``local`` so we
    never leak per-dev environment names into the Sentry dashboard.
    """
    normalised = app_env.lower()
    if normalised in _ALLOWED_ENVIRONMENTS:
        return normalised
    if normalised == "production":
        return "production"
    if normalised in {"staging", "stage"}:
        return "staging"
    return "local"


_initialised: bool = False


def init_sentry(
    *,
    component: str,
    dsn: str | None = None,
    environment: str | None = None,
    traces_sample_rate: float | None = None,
) -> bool:
    """Initialise the Sentry SDK.  Idempotent — safe to call multiple times.

    Returns ``True`` if Sentry was actually initialised (i.e. a DSN was
    available), ``False`` otherwise so callers can log a warning.
    """
    global _initialised
    if _initialised:
        return True

    # Late import so test environments that don't have the SDK installed still
    # load the module (the module is imported from ``config.py`` transitively).
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    from adcopilot.config import get_settings

    settings = get_settings()

    resolved_dsn = dsn or settings.SENTRY_DSN or os.environ.get("SENTRY_DSN")
    if not resolved_dsn:
        logger.info("sentry dsn not configured — skipping init", component=component)
        return False

    resolved_env = environment or _resolve_environment(settings.ENV)
    resolved_sample_rate = (
        traces_sample_rate if traces_sample_rate is not None else settings.SENTRY_TRACES_SAMPLE_RATE
    )
    release = _resolve_release()

    sentry_sdk.init(
        dsn=resolved_dsn,
        environment=resolved_env,
        release=release,
        traces_sample_rate=resolved_sample_rate,
        # Sensitive defaults — PII is scrubbed in before_send regardless.
        send_default_pii=False,
        attach_stacktrace=True,
        max_breadcrumbs=50,
        # sentry_sdk types ``before_send`` as a TypedDict ``Event``, but
        # dict[str, Any] is structurally compatible — cast to appease mypy
        # without requiring a runtime dependency on the private TypedDict.
        before_send=_before_send,  # type: ignore[arg-type]
        before_send_transaction=_before_send_transaction,  # type: ignore[arg-type]
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            CeleryIntegration(monitor_beat_tasks=True),
            SqlalchemyIntegration(),
            RedisIntegration(),
            LoggingIntegration(event_level=None),
        ],
    )
    sentry_sdk.set_tag("component", component)
    _initialised = True
    logger.info(
        "sentry initialised",
        component=component,
        environment=resolved_env,
        release=release,
        traces_sample_rate=resolved_sample_rate,
    )
    return True
