"""Shared content for REAUTH_REQUIRED notifications.

An account's OAuth session can be invalidated from several places (nightly
snapshot, recommendation execution, hourly anomaly detection).  All of them
flag the account ``needs_reauth`` and should surface the *same* user-facing
message, in Polish, so the user understands their automated operations are
paused until they reconnect.  Centralising the text here keeps those paths
from drifting apart.
"""

from __future__ import annotations

from adcopilot.domain.entities import GoogleAdsAccount

REAUTH_NOTIFICATION_TITLE = "Połączenie z Google Ads wygasło"


def build_reauth_notification(account: GoogleAdsAccount) -> tuple[str, str, dict]:
    """Return ``(title, body, metadata)`` for an account that needs reauth."""
    account_label = account.descriptive_name or f"ID {account.customer_id}"
    body = (
        f"Konto „{account_label}” wymaga ponownego połączenia z Google Ads. "
        "Do czasu ponownej autoryzacji automatyczne działania na tym koncie "
        "(synchronizacja danych, rekomendacje, wykrywanie anomalii) są wstrzymane. "
        "Przejdź do sekcji Konta Google Ads i kliknij „Reauth”, aby przywrócić połączenie."
    )
    metadata = {
        "account_id": str(account.id),
        "customer_id": account.customer_id,
    }
    return REAUTH_NOTIFICATION_TITLE, body, metadata
