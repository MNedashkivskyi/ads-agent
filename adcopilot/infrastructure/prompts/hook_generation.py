"""Hook generation prompt — angle-anchored, surface-aware, char-limited.

Generate hooks anchored on the customer's *state* (their pain, the alternatives
that failed them, the result they want), never on the product. Each hook is
tagged with its angle and the surface it targets and must respect that surface's
character limit. A ``focus`` line lets the caller steer generation toward one ad
group's theme (the problem terms, or the buying intent) so each group gets its
own tailored, distinct headlines.
"""

from __future__ import annotations

import json

HOOK_GENERATION_PROMPT_KEY = "cie_hook_generation_v1"

SYSTEM_PROMPT = (
    "Jesteś światowej klasy copywriterem reklam Google Ads dla polskich firm "
    "MŚP. Tworzysz HOOKI zakotwiczone w STANIE klienta — jego konkretnym bólu, w "
    "tym co już bezskutecznie próbował, w efekcie którego pragnie — a NIGDY w "
    "samym produkcie.\n\n"
    "ZASADY JAKOŚCI (bezwzględne):\n"
    "- Konkret zamiast ogólników. ŹLE: 'Czy to boli?'. DOBRZE: 'Cellulit, który "
    "nie znika?'.\n"
    "- Każdy nagłówek musi działać samodzielnie i być mocny.\n"
    "- Odwołuj się do realnej usługi/efektu i słów klienta, nie do pustych pytań.\n"
    "- Różnicuj nagłówki — żadnych powtórzeń tej samej myśli.\n"
    "- Bez obietnic medycznych ('wyleczy', '100% skuteczności') i oceniania ciała.\n"
    "- Nagłówki ≤ 30 znaków, opisy ≤ 90 znaków. Trzymaj limity bezwzględnie.\n\n"
    "Każdy hook oznacz kątem (angle) i powierzchnią (surface). Odpowiadasz "
    "WYŁĄCZNIE tablicą JSON, bez markdown, bez komentarzy."
)

USER_TEMPLATE = (
    "USŁUGA: {service}\n"
    "BRANŻA: {vertical}\n"
    "JĘZYK: {language}\n"
    "PROBLEMY KLIENTÓW:\n{problems}\n\n"
    "{focus}"
    "KĄTY (angle) i liczba NAGŁÓWKÓW do wygenerowania na każdy:\n{angles}\n\n"
    "Dla każdego kąta wygeneruj wskazaną liczbę nagłówków (surface: HEADLINE, "
    "≤30 znaków) ORAZ 1–2 opisy (surface: DESCRIPTION, ≤90 znaków). Opisy mogą "
    "łączyć korzyść z wezwaniem do działania.\n\n"
    "Przykłady jakości:\n"
    '- {{"text": "Cellulit, który nie znika?", "angle": "PAIN", "surface": "HEADLINE"}}\n'
    '- {{"text": "Diety i ćwiczenia zawiodły?", "angle": "FAILED_ALTERNATIVE", '
    '"surface": "HEADLINE"}}\n'
    '- {{"text": "Gładsza skóra w 4 tygodnie", "angle": "RESULT", "surface": "HEADLINE"}}\n'
    '- {{"text": "Drenaż limfatyczny bez bólu i rekonwalescencji. Umów wizytę '
    'online.", "angle": "OBJECTION", "surface": "DESCRIPTION"}}\n\n'
    "ODPOWIEDŹ — wyłącznie tablica JSON:\n"
    '[{{"text": "...", "angle": "PAIN", "surface": "HEADLINE"}}]'
)


def _format_angles(angle_allocation: dict[str, int]) -> str:
    return "\n".join(f"- {angle}: {count}" for angle, count in angle_allocation.items())


def _format_problems(problems: list[str]) -> str:
    if not problems:
        return "(brak — wywnioskuj z usługi i branży)"
    return "\n".join(f"- {p}" for p in problems)


def _format_focus(focus: str | None) -> str:
    if not focus:
        return ""
    return f"FOKUS TEJ GRUPY REKLAM:\n{focus}\n\n"


def render(
    *,
    service: str,
    vertical: str,
    problems: list[str],
    angle_allocation: dict[str, int],
    surfaces: list[str],
    language: str = "pl",
    focus: str | None = None,
    system_template: str | None = None,
    user_template: str | None = None,
) -> tuple[str, str]:
    system = system_template or SYSTEM_PROMPT
    template = user_template or USER_TEMPLATE
    # The DB-seeded template predates {focus}/{surfaces}; only pass kwargs it uses.
    fmt: dict[str, str] = {
        "service": service,
        "vertical": vertical,
        "language": language,
        "problems": _format_problems(problems),
        "angles": _format_angles(angle_allocation),
        "focus": _format_focus(focus),
        "surfaces": "\n".join(surfaces),
    }
    try:
        user = template.format(**fmt)
    except KeyError:
        # Older template references a field we didn't supply — fall back to code default.
        user = USER_TEMPLATE.format(**fmt)
    return system, user


SEED_CONTENT = json.dumps(
    {"system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE}, ensure_ascii=False
)
