"""Polish advertising compliance validators.

Covers: Ustawa o zwalczaniu nieuczciwej konkurencji + Kodeks Etyki Reklamy.
Pattern matching is case-insensitive and handles Polish diacritics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    HIGH = "WYSOKI"
    MEDIUM = "ŚREDNI"
    LOW = "NISKI"


@dataclass(frozen=True)
class ComplianceWarning:
    severity: Severity
    message: str
    suggestion: str


def _match(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE))


def _any_match(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        if _match(p, text):
            return p
    return None


# ---------------------------------------------------------------------------
# Vertical-specific validators
# ---------------------------------------------------------------------------

_MEDICAL_HEALTH_CLAIMS: list[tuple[str, str, str]] = [
    (
        r"wyle[cć]zy",
        Severity.HIGH,
        "Nagłówek zawiera roszczenie zdrowotne 'wyleczy/wyleczymy'. Sugestia: 'Profesjonalna pomoc medyczna'",
    ),
    (
        r"gwarantowany efekt",
        Severity.HIGH,
        "Fraza 'gwarantowany efekt' narusza zasady etyki reklamy. Sugestia: 'Skuteczna terapia'",
    ),
    (
        r"100%\s*skuteczno[śs]ci?",
        Severity.HIGH,
        "Twierdzenie '100% skuteczności' jest nieweryfikowalne. Sugestia: 'Wysoka skuteczność potwierdzona badaniami'",
    ),
    (
        r"najlepszy lekarz",
        Severity.MEDIUM,
        "Superlatyw 'najlepszy lekarz' bez certyfikowanego rankingu. Sugestia: 'Doświadczony lekarz specjalista'",
    ),
    (
        r"\bnajlepszy\b",
        Severity.MEDIUM,
        "Nieuzasadniony superlatyw 'najlepszy'. Sugestia: użyj konkretnych atrybutów",
    ),
    (r"\bjedyny\b", Severity.MEDIUM, "Twierdzenie 'jedyny' wymaga weryfikowalnych dowodów"),
    (
        r"\bnajpewniejszy\b",
        Severity.MEDIUM,
        "Superlatyw 'najpewniejszy' bez certyfikowanego rankingu",
    ),
    (r"bez skierowania", Severity.LOW, "Rozważ dodanie: 'konsultacja z lekarzem zalecana'"),
    (
        r"natychmiastowe wyzdrowienie",
        Severity.HIGH,
        "Twierdzenie o 'natychmiastowym wyzdrowieniu' jest wprowadzające w błąd",
    ),
    (r"gwarantujemy zdrowie", Severity.HIGH, "Gwarancja zdrowia narusza przepisy reklamowe"),
]

_MEDICAL_DISCLAIMER_MISSING = (
    Severity.LOW,
    "Reklama usług medycznych powinna zawierać zastrzeżenie: 'Skonsultuj się z lekarzem'",
    "Dodaj: 'Skonsultuj się z lekarzem przed podjęciem leczenia'",
)

_FINANCIAL_LEGAL_CLAIMS: list[tuple[str, str, str]] = [
    (
        r"gwarantowany zysk",
        Severity.HIGH,
        "Fraza 'gwarantowany zysk' narusza prawo reklamowe. Sugestia: 'Możliwy zysk przy odpowiednim zarządzaniu'",
    ),
    (
        r"pewna inwestycja",
        Severity.HIGH,
        "Twierdzenie 'pewna inwestycja' jest mylące. Sugestia: 'Perspektywiczna inwestycja'",
    ),
    (
        r"bez ryzyka",
        Severity.HIGH,
        "Każda inwestycja wiąże się z ryzykiem. Sugestia: 'Inwestycja z zarządzaniem ryzykiem'",
    ),
    (
        r"zarobisz\s+\d+",
        Severity.HIGH,
        "Obietnica konkretnych zarobków jest nieuczciwa. Sugestia: 'Możliwość wzrostu kapitału'",
    ),
    (r"zysk\s+\d+%", Severity.HIGH, "Obiecany % zysku wymaga zastrzeżenia o ryzyku"),
    (
        r"podwoisz\s+(swój\s+)?kapita[łl]",
        Severity.HIGH,
        "Obietnica podwojenia kapitału jest unikana. Sugestia: 'Potencjał wzrostu kapitału'",
    ),
    (
        r"gwarantujemy wygraną",
        Severity.HIGH,
        "Gwarancja wygranej sprawy sądowej narusza Kodeks Etyki Reklamy. Sugestia: 'Skuteczna pomoc prawna'",
    ),
    (
        r"100%\s*skuteczno[śs][cć]\s*(w|w\s*sprawach)?",
        Severity.HIGH,
        "Twierdzenie '100% skuteczności' dla usług prawnych jest nieuczciwe",
    ),
    (
        r"pewna wygrana",
        Severity.HIGH,
        "Twierdzenie o 'pewnej wygranej' narusza zasady etyki prawniczej",
    ),
    (
        r"gwarantujemy wynik",
        Severity.MEDIUM,
        "Gwarancja wyniku sprawy jest ryzykowna prawnie. Sugestia: 'Dążymy do najlepszego wyniku'",
    ),
]

_FINANCIAL_DISCLAIMER = (
    Severity.LOW,
    "Usługi finansowe powinny zawierać zastrzeżenie o ryzyku",
    "Dodaj: 'Inwestowanie wiąże się z ryzykiem utraty kapitału'",
)


# ---------------------------------------------------------------------------
# General validator (all verticals)
# ---------------------------------------------------------------------------

_GENERAL_CLAIMS: list[tuple[str, str, str]] = [
    (
        r"lepszy ni[zż]\s+\w+",
        Severity.MEDIUM,
        "Twierdzenie porównawcze 'lepszy niż' wymaga weryfikowalnych dowodów",
    ),
    (
        r"ta[nń]szy od konkurencji",
        Severity.MEDIUM,
        "Twierdzenie o niższej cenie niż konkurencja wymaga aktualnych dowodów",
    ),
    (
        r"\bza darmo\b",
        Severity.HIGH,
        "Fraza 'za darmo' jest OK tylko gdy usługa jest rzeczywiście bezpłatna",
    ),
    (
        r"\bdarmowy\b",
        Severity.HIGH,
        "Słowo 'darmowy' jest OK tylko gdy usługa jest rzeczywiście bezpłatna",
    ),
    (
        r"\bdarmowa\b",
        Severity.HIGH,
        "Słowo 'darmowa' jest OK tylko gdy usługa jest rzeczywiście bezpłatna",
    ),
    (
        r"[A-ZŁÓŚĄĘŻŹ]{4,}",
        Severity.LOW,
        "WSZYSTKIE WIELKIE LITERY w nagłówku naruszają politykę Google Ads. Sugestia: użyj normalnej wielkości liter",
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _check_patterns(
    text: str,
    patterns: list[tuple[str, str, str]],
) -> list[ComplianceWarning]:
    warnings: list[ComplianceWarning] = []
    for pattern, severity, message in patterns:
        if _match(pattern, text):
            parts = message.split("Sugestia:", 1)
            suggestion = parts[1].strip() if len(parts) > 1 else ""
            msg = parts[0].strip()
            warnings.append(
                ComplianceWarning(severity=Severity(severity), message=msg, suggestion=suggestion)
            )
    return warnings


def validate_ad_copy(
    headlines: list[str],
    descriptions: list[str],
    vertical: str | None,
) -> list[ComplianceWarning]:
    """Run compliance validators against ad copy and return warnings.

    Vertical-specific validators are added on top of the general validator.
    Unknown/None vertical gets only the general validator.
    """
    combined_text = " ".join(headlines + descriptions)
    warnings: list[ComplianceWarning] = []

    # General validator — all verticals
    warnings.extend(_check_patterns(combined_text, _GENERAL_CLAIMS))

    normalized_vertical = (vertical or "").lower()

    if normalized_vertical in ("lekarz", "medical"):
        warnings.extend(_check_patterns(combined_text, _MEDICAL_HEALTH_CLAIMS))
        # Require disclaimer for medical ads
        disclaimer_keywords = (
            r"skonsultuj\s+si[eę]\s+z\s+lekarzem|porada\s+lekarska|konsultacja\s+medyczna"
        )
        if not _match(disclaimer_keywords, combined_text):
            sev, msg, sug = _MEDICAL_DISCLAIMER_MISSING
            warnings.append(ComplianceWarning(severity=sev, message=msg, suggestion=sug))

    elif normalized_vertical in ("prawnik", "legal"):
        warnings.extend(_check_patterns(combined_text, _FINANCIAL_LEGAL_CLAIMS))

    elif normalized_vertical in ("e-commerce", "ecommerce", "finanse", "financial"):
        warnings.extend(_check_patterns(combined_text, _FINANCIAL_LEGAL_CLAIMS))
        # Suggest financial disclaimer
        disclaimer_keywords = r"ryzyko|inwestowanie wi[aą][zż]e si[eę]"
        if not _match(disclaimer_keywords, combined_text):
            sev, msg, sug = _FINANCIAL_DISCLAIMER
            warnings.append(ComplianceWarning(severity=sev, message=msg, suggestion=sug))

    return warnings


def format_compliance_warnings(warnings: list[ComplianceWarning]) -> str:
    """Format warnings as a Telegram-ready Polish message block."""
    if not warnings:
        return ""

    lines = ["⚠️ *Uwagi dotyczące zgodności reklamy:*"]
    for w in warnings:
        line = f"- [{w.severity}] {w.message}"
        if w.suggestion:
            line += f". Sugestia: _{w.suggestion}_"
        lines.append(line)
    return "\n".join(lines)
