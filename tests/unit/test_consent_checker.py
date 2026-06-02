from __future__ import annotations

from adcopilot.infrastructure.consent_checker import detect_measurement_signals

CONSENT_V2_HTML = """
<html><head>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('consent', 'default', {
    'ad_storage': 'denied',
    'ad_user_data': 'denied',
    'ad_personalization': 'denied',
    'analytics_storage': 'denied',
  });
</script>
<script src="https://www.googletagmanager.com/gtag/js?id=AW-123"></script>
</head><body>Sklep</body></html>
"""

OLD_CONSENT_HTML = """
<html><head><script>
  gtag('consent', 'default', { 'ad_storage': 'denied', 'analytics_storage': 'denied' });
</script></head><body>x</body></html>
"""

ENHANCED_HTML = """
<html><head><script>
  gtag('config', 'AW-123', { 'allow_enhanced_conversions': true });
</script></head><body>x</body></html>
"""

PLAIN_HTML = "<html><head></head><body>Witamy</body></html>"


def test_detects_full_consent_mode_v2() -> None:
    s = detect_measurement_signals(CONSENT_V2_HTML)
    assert s.ad_user_data is True
    assert s.ad_personalization is True
    assert s.analytics_storage is True
    assert s.consent_mode_v2 is True


def test_old_consent_is_not_v2() -> None:
    s = detect_measurement_signals(OLD_CONSENT_HTML)
    # No ad_user_data / ad_personalization -> not Consent Mode v2.
    assert s.ad_user_data is False
    assert s.ad_personalization is False
    assert s.consent_mode_v2 is False


def test_detects_enhanced_conversions_web() -> None:
    s = detect_measurement_signals(ENHANCED_HTML)
    assert s.enhanced_conversions_web is True


def test_plain_page_has_no_signals() -> None:
    s = detect_measurement_signals(PLAIN_HTML)
    assert s.consent_mode_v2 is False
    assert s.ad_user_data is False
    assert s.enhanced_conversions_web is False


def test_empty_input_is_safe() -> None:
    s = detect_measurement_signals("")
    assert s.consent_mode_v2 is False
