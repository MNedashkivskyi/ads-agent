"""assess_measurement_health — compute the measurement-health diagnostic.

Pure function over already-fetched inputs (conversion-action snapshots + a
GA4-linked flag) so it is trivially unit-testable. The API layer
(interfaces/api/measurement.py) does the I/O and calls this.

Phase 0 reports honestly on what can be derived from conversion-action
configuration + the GA4 link. Sub-scores that require deeper verification
(enhanced conversions, consent mode v2, offline-import wiring) are surfaced as
NEEDS_ATTENTION with guidance and are tightened in later phases.
"""

from __future__ import annotations

from collections.abc import Sequence

from adcopilot.domain.measurement import (
    ConversionActionSummary,
    MeasurementHealthReport,
    MeasurementStatus,
    MeasurementSubScore,
)

# Google Ads ConversionActionCategory enum names that imply a monetary value.
_VALUE_CATEGORIES = {
    "PURCHASE",
    "ADD_TO_CART",
    "BEGIN_CHECKOUT",
    "SUBSCRIBE_PAID",
    "STORE_SALE",
}

# Categories that represent lead-gen outcomes (candidates for offline import).
_LEAD_CATEGORIES = {
    "SUBMIT_LEAD_FORM",
    "PHONE_CALL_LEAD",
    "IMPORTED_LEAD",
    "BOOK_APPOINTMENT",
    "REQUEST_QUOTE",
    "SIGN_UP",
    "CONTACT",
    "QUALIFIED_LEAD",
    "CONVERTED_LEAD",
    "GET_DIRECTIONS",
}


def _classify_action_health(status: str, all_conversions: float) -> str:
    if status in ("REMOVED", "HIDDEN"):
        return "DISABLED"
    if all_conversions > 0:
        return "HEALTHY"
    return "STALE"


def _sub(key: str, label: str, status: MeasurementStatus, detail: str) -> MeasurementSubScore:
    return MeasurementSubScore(key=key, label=label, status=status, detail=detail)


def assess_measurement_health(
    conversion_actions: Sequence[object],
    *,
    ga4_linked: bool,
) -> MeasurementHealthReport:
    """Build a MeasurementHealthReport from conversion-action snapshots + GA4 link.

    ``conversion_actions`` items must expose ``name``, ``category``, ``status``
    and ``all_conversions`` (ConversionActionSnapshot satisfies this).
    """
    summaries: list[ConversionActionSummary] = []
    for s in conversion_actions:
        status = str(getattr(s, "status", ""))
        conv = float(getattr(s, "all_conversions", 0.0) or 0.0)
        summaries.append(
            ConversionActionSummary(
                name=str(getattr(s, "name", "")),
                category=str(getattr(s, "category", "")),
                status=status,
                all_conversions=conv,
                health=_classify_action_health(status, conv),
            )
        )

    enabled = [s for s in summaries if s.status not in ("REMOVED", "HIDDEN")]
    receiving = [s for s in enabled if s.all_conversions > 0]
    has_value_category = any(s.category in _VALUE_CATEGORIES for s in enabled)
    has_lead_category = any(s.category in _LEAD_CATEGORIES for s in enabled)

    subscores: list[MeasurementSubScore] = []

    # 1) conversion_actions — is there an enabled action actually recording?
    if not summaries:
        subscores.append(
            _sub(
                "conversion_actions",
                "Akcje konwersji",
                MeasurementStatus.MISSING,
                "Konto nie ma żadnej akcji konwersji. Skonfiguruj śledzenie konwersji "
                "(np. przez Google Tag Manager) — bez tego Smart Bidding działa „na ślepo”.",
            )
        )
    elif not receiving:
        subscores.append(
            _sub(
                "conversion_actions",
                "Akcje konwersji",
                MeasurementStatus.NEEDS_ATTENTION,
                "Masz akcje konwersji, ale żadna nie zarejestrowała konwersji w ostatnich 7 dniach. "
                "Sprawdź, czy tag działa poprawnie.",
            )
        )
    else:
        subscores.append(
            _sub(
                "conversion_actions",
                "Akcje konwersji",
                MeasurementStatus.HEALTHY,
                f"{len(receiving)} aktywnych akcji rejestruje konwersje.",
            )
        )

    # 2) value_tracking — full value verification lands in Phase 5; Phase 0 flags it.
    if not summaries:
        subscores.append(
            _sub(
                "value_tracking",
                "Śledzenie wartości",
                MeasurementStatus.MISSING,
                "Brak konwersji, więc brak wartości. Po dodaniu śledzenia ustaw wartości konwersji.",
            )
        )
    elif has_value_category:
        subscores.append(
            _sub(
                "value_tracking",
                "Śledzenie wartości",
                MeasurementStatus.NEEDS_ATTENTION,
                "Wykryto akcje zakupowe — potwierdź, że przekazują rzeczywistą wartość "
                "(przychód/marżę), aby umożliwić strategię tROAS.",
            )
        )
    else:
        subscores.append(
            _sub(
                "value_tracking",
                "Śledzenie wartości",
                MeasurementStatus.NEEDS_ATTENTION,
                "Konwersje nie mają przypisanej wartości. Dla lead-gen przypisz wartość "
                "biznesową (np. wartość leada/klienta), aby włączyć licytację opartą na wartości.",
            )
        )

    # 3) enhanced_conversions — verified in Phase 3.
    subscores.append(
        _sub(
            "enhanced_conversions",
            "Konwersje rozszerzone",
            MeasurementStatus.MISSING if not summaries else MeasurementStatus.NEEDS_ATTENTION,
            "Włącz konwersje rozszerzone (hashowane dane first-party) dla lepszego dopasowania "
            "i odzyskania konwersji utraconych przez ograniczenia plików cookie.",
        )
    )

    # 4) consent_mode_v2 — verified in Phase 4.
    subscores.append(
        _sub(
            "consent_mode_v2",
            "Tryb zgody v2",
            MeasurementStatus.NEEDS_ATTENTION,
            "Nie potwierdzono sygnałów Consent Mode v2 (ad_user_data, ad_personalization). "
            "Jest wymagany w EOG — bez niego tracisz pomiar i remarketing.",
        )
    )

    # 5) ga4_link — real signal.
    subscores.append(
        _sub(
            "ga4_link",
            "Połączenie GA4",
            MeasurementStatus.HEALTHY if ga4_linked else MeasurementStatus.MISSING,
            "GA4 jest połączone."
            if ga4_linked
            else "Połącz Google Analytics 4, aby wzbogacić pomiar i analizę ścieżek.",
        )
    )

    # 6) oci_readiness — wired in Phase 2.
    if has_lead_category:
        subscores.append(
            _sub(
                "oci_readiness",
                "Gotowość do importu offline",
                MeasurementStatus.NEEDS_ATTENTION,
                "Masz akcje typu lead. Skonfiguruj przechwytywanie GCLID na formularzu, aby "
                "importować rzeczywiste zamknięcia sprzedaży (Offline Conversion Import).",
            )
        )
    else:
        subscores.append(
            _sub(
                "oci_readiness",
                "Gotowość do importu offline",
                MeasurementStatus.MISSING,
                "Brak akcji typu lead. Import konwersji offline dotyczy głównie lead-gen.",
            )
        )

    overall = _overall(subscores)
    return MeasurementHealthReport(
        overall_status=overall,
        subscores=subscores,
        conversion_actions=summaries,
    )


def _overall(subscores: list[MeasurementSubScore]) -> MeasurementStatus:
    statuses = {s.status for s in subscores}
    # No tracking at all → the whole foundation is missing.
    ca = next((s for s in subscores if s.key == "conversion_actions"), None)
    if ca is not None and ca.status is MeasurementStatus.MISSING:
        return MeasurementStatus.MISSING
    if statuses == {MeasurementStatus.HEALTHY}:
        return MeasurementStatus.HEALTHY
    return MeasurementStatus.NEEDS_ATTENTION
