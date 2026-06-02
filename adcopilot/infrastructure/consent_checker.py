"""Detect Consent Mode v2 + Enhanced Conversions (web) signals from page HTML.

Phase 4 verification: scans a site's HTML/inline scripts for the consent and
enhanced-conversions signals Google Ads needs in the EEA. Pure + string-based
so it's deterministic and unit-testable; the fetcher (consent_fetcher) supplies
the HTML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)

# A gtag/dataLayer consent call, e.g. gtag('consent', 'default'|'update', {...}).
_CONSENT_CALL = re.compile(r"""consent['"]?\s*,\s*['"](default|update)['"]""", re.IGNORECASE)
_AD_USER_DATA = re.compile(r"ad_user_data", re.IGNORECASE)
_AD_PERSONALIZATION = re.compile(r"ad_personalization", re.IGNORECASE)
_ANALYTICS_STORAGE = re.compile(r"analytics_storage", re.IGNORECASE)
_ENHANCED = re.compile(r"allow_enhanced_conversions|enhanced_conversion", re.IGNORECASE)


@dataclass
class ConsentSignals:
    ad_user_data: bool = False
    ad_personalization: bool = False
    analytics_storage: bool = False
    consent_mode_v2: bool = False
    enhanced_conversions_web: bool = False


def detect_measurement_signals(html: str | None) -> ConsentSignals:
    if not html:
        return ConsentSignals()
    ad_user_data = bool(_AD_USER_DATA.search(html))
    ad_personalization = bool(_AD_PERSONALIZATION.search(html))
    analytics_storage = bool(_ANALYTICS_STORAGE.search(html))
    has_consent_call = bool(_CONSENT_CALL.search(html))
    # Consent Mode v2 specifically requires the ad_user_data + ad_personalization
    # signals inside a consent call — the v1 → v2 distinction.
    consent_mode_v2 = has_consent_call and ad_user_data and ad_personalization
    return ConsentSignals(
        ad_user_data=ad_user_data,
        ad_personalization=ad_personalization,
        analytics_storage=analytics_storage,
        consent_mode_v2=consent_mode_v2,
        enhanced_conversions_web=bool(_ENHANCED.search(html)),
    )


async def fetch_measurement_signals(url: str, *, timeout: float = 8.0) -> ConsentSignals:
    """Fetch a URL and detect signals. Best-effort: returns empty signals on any
    error so the diagnostic degrades gracefully rather than failing."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": "AdswiseMeasurementBot/1.0"}
        ) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                return ConsentSignals()
            return detect_measurement_signals(response.text)
    except Exception as exc:  # noqa: BLE001 — diagnostic must not hard-fail
        logger.warning("consent_signal_fetch_failed", url=url, error=str(exc))
        return ConsentSignals()
