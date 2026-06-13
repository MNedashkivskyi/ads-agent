"""Keyword generation prompt — customer-problem-anchored, intent-tagged.

Forces the model to think from the customer's *problem*, not the product. The
single most important instruction: the customer often does NOT know the product
name — they search their symptom ("nie mogę schudnąć z ud") or the effect they
want ("drenaż limfatyczny"), not "icoone". Output is strict JSON tagged by
intent-type so each candidate can be attributed to its dimension value later.
"""

from __future__ import annotations

import json

KEYWORD_GENERATION_PROMPT_KEY = "cie_keyword_generation_v1"

SYSTEM_PROMPT = (
    "Jesteś ekspertem od Google Ads i badania słów kluczowych dla polskich firm "
    "MŚP. Twoim zadaniem jest wygenerowanie słów kluczowych zakotwiczonych w "
    "PROBLEMIE i INTENCJI klienta — a nie w nazwie produktu.\n\n"
    "KLUCZOWA ZASADA: klient bardzo często NIE zna nazwy produktu ani marki. "
    "Szuka swojego problemu lub efektu, którego pragnie. Przykład: nikt nie "
    "wpisuje 'icoone', wszyscy wpisują 'drenaż limfatyczny' albo 'cellulit po "
    "ciąży'. Generuj tak, jak myśli i pisze realny klient.\n\n"
    "Każde słowo kluczowe oznacz jednym z trzech typów intencji:\n"
    "- BRAND: klient zna już produkt/markę (np. 'icoone Warszawa').\n"
    "- INTENT: usługa lub efekt, którego szuka, nie znając produktu "
    "(np. 'drenaż limfatyczny', 'modelowanie sylwetki').\n"
    "- PROBLEM: jak klient opisuje swój ból/problem "
    "(np. 'nie mogę schudnąć z ud', 'cellulit po ciąży').\n\n"
    "Odpowiadasz WYŁĄCZNIE w formacie JSON — tablica obiektów, bez komentarzy, "
    "bez bloków markdown, bez tekstu przed ani po."
)

# NOTE: literal JSON braces are doubled for str.format; named fields are single.
USER_TEMPLATE = (
    "USŁUGA: {service}\n"
    "BRANŻA: {vertical}\n"
    "JĘZYK SŁÓW KLUCZOWYCH: {language}\n"
    "PROBLEMY KLIENTÓW (materiał źródłowy):\n{problems}\n\n"
    "WYGENERUJ DOKŁADNIE tyle słów kluczowych w każdym typie intencji:\n"
    "{allocation}\n\n"
    "Przykłady (branża beauty, produkt 'icoone'):\n"
    '- BRAND: {{"phrase": "icoone warszawa", "intent": "BRAND", "reasoning": '
    '"klient zna markę"}}\n'
    '- INTENT: {{"phrase": "drenaż limfatyczny", "intent": "INTENT", "reasoning": '
    '"szuka efektu, nie zna produktu"}}\n'
    '- PROBLEM: {{"phrase": "jak pozbyć się cellulitu z ud", "intent": "PROBLEM", '
    '"reasoning": "opisuje swój problem"}}\n\n'
    "WYMAGANIA:\n"
    "- Każda fraza w języku: {language}.\n"
    "- Frazy 2–6 słów, realne zapytania wyszukiwania, bez znaków specjalnych.\n"
    "- Nie powtarzaj fraz. Nie dodawaj nazw konkurencji.\n"
    "- Pole 'reasoning' krótkie (max 8 słów).\n\n"
    "ODPOWIEDŹ — wyłącznie tablica JSON:\n"
    '[{{"phrase": "...", "intent": "INTENT|PROBLEM|BRAND", "reasoning": "..."}}]'
)


def _format_allocation(intent_allocation: dict[str, int]) -> str:
    return "\n".join(f"- {intent}: {count}" for intent, count in intent_allocation.items())


def _format_problems(problems: list[str]) -> str:
    if not problems:
        return "(brak — wywnioskuj z usługi i branży)"
    return "\n".join(f"- {p}" for p in problems)


def render_user_prompt(
    *,
    service: str,
    vertical: str,
    problems: list[str],
    intent_allocation: dict[str, int],
    language: str = "pl",
) -> str:
    """Render the user prompt with all variables filled in."""
    return USER_TEMPLATE.format(
        service=service,
        vertical=vertical,
        language=language,
        problems=_format_problems(problems),
        allocation=_format_allocation(intent_allocation),
    )


def render(
    *,
    service: str,
    vertical: str,
    problems: list[str],
    intent_allocation: dict[str, int],
    language: str = "pl",
    system_template: str | None = None,
    user_template: str | None = None,
) -> tuple[str, str]:
    """Return ``(system, user)`` prompts. Optionally use DB-sourced templates.

    ``user_template`` (when provided, e.g. from the versioned DB prompt) is
    rendered with the same variables; otherwise the code default is used.
    """
    system = system_template or SYSTEM_PROMPT
    template = user_template or USER_TEMPLATE
    user = template.format(
        service=service,
        vertical=vertical,
        language=language,
        problems=_format_problems(problems),
        allocation=_format_allocation(intent_allocation),
    )
    return system, user


# The full text seeded into prompt_versions (system + a marker + user template),
# so the canonical wording is versioned in the DB per the prompt-versioning rule.
SEED_CONTENT = json.dumps(
    {"system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE},
    ensure_ascii=False,
)
