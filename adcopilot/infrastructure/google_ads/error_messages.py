"""Human-readable (Polish) translation of Google Ads campaign-creation errors.

The Google Ads API surfaces failures as ``GoogleAdsException`` whose string
representation embeds the structured error enum (e.g. ``campaign_error:
DUPLICATE_CAMPAIGN_NAME``) plus an English message. End users should never see
that raw payload — per the project's error-surfacing rule every campaign
failure must produce a clear, human-readable Polish notification.

This module enumerates the failure modes we have seen (or can reasonably
expect) when creating a Search campaign and maps each to a Polish explanation
with a concrete next step. Detection is done on the lower-cased exception text
so it works whether the error arrives as a ``GoogleAdsException``, a wrapped
``GoogleAdsUnavailable``, or a plain string — we never depend on the proto
internals, which differ across library versions.

Edge cases handled (token -> meaning):

  DUPLICATE_CAMPAIGN_NAME      a campaign with that name already exists
  DUPLICATE_NAME / budget dup  a budget/resource name is already taken
  invalid_grant / unauthent.   OAuth refresh token expired or revoked
  developer token / not approved   dev token is a test/unapproved token
  customer_not_enabled / suspended account not active (billing/verification)
  billing / payments_profile   no active billing set up on the account
  permission_denied            no write access to this Google Ads account
  resource_exhausted / quota   API quota / rate limit hit
  conversion / bidding_strategy bidding needs conversion tracking first
  budget ... too_low / amount  daily budget below the allowed minimum
  internal / unavailable / deadline  transient Google-side outage
  (anything else)              generic fallback with retry guidance
"""

from __future__ import annotations

__all__ = [
    "is_duplicate_campaign_name",
    "humanize_google_ads_error",
]

# Generic fallback shown when we cannot classify the failure.
_GENERIC_PL = (
    "Wystąpił nieoczekiwany błąd po stronie Google Ads. "
    "Spróbuj ponownie za chwilę, a jeśli problem się powtórzy — skontaktuj się z pomocą techniczną."
)


def _text(exc: object) -> str:
    """Return a lower-cased searchable representation of *exc*."""
    return str(exc).lower()


def is_duplicate_campaign_name(exc: object) -> bool:
    """True when the failure is specifically a campaign-name collision."""
    return "duplicate_campaign_name" in _text(exc)


# Ordered (token-predicate, Polish message) rules. The first match wins, so
# more specific tokens must come before broader ones.
def _matches(text: str, *tokens: str) -> bool:
    return any(tok in text for tok in tokens)


def humanize_google_ads_error(exc: object) -> str:
    """Translate a Google Ads failure into a clear Polish, user-facing reason.

    Always returns a non-empty string; falls back to a generic retry message
    for failures we do not specifically recognise.
    """
    t = _text(exc)

    # --- Naming collisions ---
    if "duplicate_campaign_name" in t:
        return (
            "Kampania o tej nazwie już istnieje na Twoim koncie Google Ads. "
            "Zmień nazwę kampanii (np. dodaj rok lub lokalizację) i spróbuj ponownie."
        )
    if _matches(t, "duplicate_name", "duplicate budget", "name_already_used"):
        return (
            "Zasób o tej nazwie (np. budżet) już istnieje na koncie. "
            "Spróbuj ponownie — nazwa zostanie automatycznie odróżniona."
        )

    # --- Authentication / authorisation ---
    if _matches(
        t,
        "invalid_grant",
        "unauthenticated",
        "token has been expired or revoked",
        "oauth_token_invalid",
        "authenticationerror",
        "invalid credentials",
        "access_denied",
    ):
        return (
            "Połączenie z kontem Google Ads wygasło lub zostało cofnięte. "
            "Połącz konto Google Ads ponownie w ustawieniach i spróbuj jeszcze raz."
        )
    if _matches(t, "developer token", "developertoken", "developer_token", "not approved", "test account"):
        return (
            "Token deweloperski Google Ads nie jest jeszcze zatwierdzony do działania na żywo. "
            "Skontaktuj się z pomocą techniczną — to ograniczenie po stronie integracji, nie Twojego konta."
        )
    if _matches(t, "user_permission_denied", "permission_denied", "not_ad_user_login_customer"):
        return (
            "Brak uprawnień do zapisu na tym koncie Google Ads. "
            "Upewnij się, że połączone konto ma dostęp na poziomie administratora/standardowym i spróbuj ponownie."
        )

    # --- Account state / billing ---
    if _matches(t, "customer_not_enabled", "account_suspended", "suspended", "not_active", "billing_setup"):
        return (
            "Konto Google Ads nie jest w pełni aktywne (np. wymaga weryfikacji lub konfiguracji). "
            "Dokończ konfigurację konta w panelu Google Ads i spróbuj ponownie."
        )
    if _matches(t, "missing_billing", "payments_profile", "billing", "no_payment", "payment"):
        return (
            "Na koncie Google Ads nie skonfigurowano płatności. "
            "Dodaj metodę płatności w panelu Google Ads, a następnie ponów próbę."
        )

    # --- Conversion tracking / bidding ---
    if _matches(t, "conversion_tracking", "no_conversion", "bidding_strategy", "requires_conversion"):
        return (
            "Wybrana strategia ustalania stawek wymaga skonfigurowanego śledzenia konwersji. "
            "Skonfiguruj śledzenie konwersji lub wybierz prostszą strategię (np. maksymalizacja kliknięć)."
        )

    # --- Budget constraints ---
    if _matches(t, "too_low", "budget_amount", "amount_micros", "below_minimum"):
        return (
            "Dzienny budżet jest zbyt niski dla wymagań Google Ads. "
            "Zwiększ miesięczny budżet kampanii i spróbuj ponownie."
        )

    # --- Quota / rate limiting ---
    if _matches(t, "resource_exhausted", "rate_exceeded", "quota", "too_many_requests"):
        return (
            "Przekroczono chwilowy limit zapytań do Google Ads. "
            "Odczekaj kilka minut i spróbuj ponownie."
        )

    # --- Transient Google-side problems ---
    if _matches(t, "internal_error", "unavailable", "deadline_exceeded", "transient_error", "internal"):
        return (
            "Google Ads chwilowo nie odpowiada. "
            "To zwykle przejściowy problem — spróbuj ponownie za kilka minut."
        )

    return _GENERIC_PL
