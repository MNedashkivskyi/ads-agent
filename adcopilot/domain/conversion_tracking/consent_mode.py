"""Consent Mode v2 setup snippet (Phase 4).

Returns the gtag consent-default block a site must load before any Google tag,
declaring the v2 signals (ad_user_data, ad_personalization). The user wires
their consent banner to call gtag('consent', 'update', ...) on acceptance.
"""

from __future__ import annotations

CONSENT_MODE_V2_SNIPPET = """<!-- Google Consent Mode v2 — wklej w <head> PRZED tagami Google (gtag/GTM) -->
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('consent', 'default', {
    'ad_storage': 'denied',
    'ad_user_data': 'denied',
    'ad_personalization': 'denied',
    'analytics_storage': 'denied',
    'wait_for_update': 500
  });
</script>
<!-- Po wyrażeniu zgody przez użytkownika wywołaj: -->
<!-- gtag('consent', 'update', { 'ad_storage':'granted', 'ad_user_data':'granted',
     'ad_personalization':'granted', 'analytics_storage':'granted' }); -->
"""

INSTRUCTIONS_PL = (
    "Wklej ten kod w sekcji <head> swojej strony, przed wszystkimi tagami Google. "
    "Następnie połącz go ze swoim banerem zgody (CMP): po akceptacji wywołaj "
    "gtag('consent', 'update', ...) z wartościami 'granted'. Consent Mode v2 jest "
    "wymagany w EOG dla pomiaru i remarketingu."
)


def consent_mode_v2_snippet() -> str:
    return CONSENT_MODE_V2_SNIPPET
