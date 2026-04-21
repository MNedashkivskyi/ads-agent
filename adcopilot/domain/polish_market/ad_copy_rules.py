"""Polish ad copy patterns, CTA verbs, and character-limit helpers."""

from __future__ import annotations

POLISH_CTAS: dict[str, list[str]] = {
    "Call": ["Zadzwoń teraz", "Zadzwoń", "Umów rozmowę"],
    "Book": ["Umów wizytę", "Zarezerwuj", "Umów się"],
    "Purchase": ["Kup teraz", "Zamów", "Dodaj do koszyka"],
    "Visit website": ["Sprawdź ofertę", "Zobacz więcej", "Dowiedz się więcej"],
    "Sign up": ["Zarejestruj się", "Zapisz się", "Dołącz"],
    "Contact": ["Skontaktuj się", "Napisz do nas", "Zapytaj o cenę"],
    "Get offer": ["Poproś o wycenę", "Pobierz ofertę", "Uzyskaj rabat"],
}

# Flat list for CTA presence detection
POLISH_CTA_VERBS: list[str] = [
    verb.lower()
    for verbs in POLISH_CTAS.values()
    for verb in verbs
]

HEADLINE_MAX_CHARS = 30
DESCRIPTION_MAX_CHARS = 90


def headline_ok(text: str) -> bool:
    return len(text) <= HEADLINE_MAX_CHARS


def description_ok(text: str) -> bool:
    return len(text) <= DESCRIPTION_MAX_CHARS
