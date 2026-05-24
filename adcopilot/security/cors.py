"""CORS allow-list construction.

Centralising this in a pure function lets us unit-test the rule
"production only allows APP_URL" without spinning up the FastAPI app.

Rules
-----
1. In ``production`` the *only* accepted origin is ``settings.APP_URL``.
   If ``APP_URL`` is unset in production this is a fatal misconfiguration —
   we ``raise RuntimeError`` rather than fall through to a wider list,
   because a silent fallback would re-open the browser to local origins
   in a prod deployment.
2. In other environments (``dev``, ``local``, ``staging``, ``test``) the
   localhost dev origins are allowed, plus ``APP_URL`` if set.
3. The empty string, ``"*"``, and any form of wildcard are always
   rejected — ``CORSMiddleware`` with ``allow_credentials=True`` and
   ``*`` is rejected by browsers anyway, but we enforce it explicitly
   so a future misconfiguration surfaces at app startup.
"""

from __future__ import annotations

from adcopilot.config import Settings

_DEV_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://localhost:5173",
    "https://adswise.xyz",
    "https://www.adswise.xyz",
    "https://approve-ads-bot-dev.up.railway.app",
)

_DISALLOWED_ORIGIN_VALUES: frozenset[str] = frozenset({"", "*", "null"})


def _normalise(origin: str) -> str:
    return origin.strip().rstrip("/")


def build_cors_allowed_origins(settings: Settings) -> list[str]:
    """Return the exact CORS allow-list for the current environment.

    Raises :class:`RuntimeError` when the configuration cannot produce a
    safe allow-list (e.g. ``APP_URL`` unset in production, or any origin
    equal to ``"*"``).
    """
    app_url = _normalise(settings.APP_URL) if settings.APP_URL else ""

    if settings.is_production:
        if not app_url:
            raise RuntimeError(
                "APP_URL must be set in production — CORS refuses to "
                "fall back to localhost origins in a prod deployment."
            )
        if app_url in _DISALLOWED_ORIGIN_VALUES:
            raise RuntimeError(f"Invalid CORS origin for production: {app_url!r}")
        return [app_url]

    # Non-production: localhost dev servers + APP_URL if set.
    origins: list[str] = list(_DEV_ORIGINS)
    if app_url and app_url not in _DISALLOWED_ORIGIN_VALUES:
        origins.append(app_url)
    return origins


def is_allowed_origin(origin: str, settings: Settings) -> bool:
    """Check if an origin is allowed — used by middleware for dynamic CORS."""
    allowed = build_cors_allowed_origins(settings)
    normalised = _normalise(origin)
    return normalised in allowed
