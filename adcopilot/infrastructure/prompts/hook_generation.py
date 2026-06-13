"""Hook generation prompt — angle-anchored, surface-aware, char-limited.

Generate hooks anchored on the customer's *state* (their pain, the alternatives
that failed them, the result they want), never on the product. Each hook is
tagged with its angle and the surface it targets and must respect that surface's
character limit.
"""

from __future__ import annotations

import json

HOOK_GENERATION_PROMPT_KEY = "cie_hook_generation_v1"

SYSTEM_PROMPT = (
    "Jesteś światowej klasy copywriterem reklam Google Ads dla polskich firm "
    "MŚP. Tworzysz HOOKI zakotwiczone w STANIE klienta — jego bólu, w tym co już "
    "bezskutecznie próbował, w efekcie którego pragnie — a NIGDY w samym "
    "produkcie. Hook 'Cellulit, który nie znika?' konwertuje; 'Icoone — umów "
    "wizytę' jest szary.\n\n"
    "Każdy hook oznacz kątem (angle) i powierzchnią (surface). Trzymaj się "
    "limitów znaków. Bądź odważny i konkretny — unikaj ogólników. Bez obietnic "
    "medycznych typu 'wyleczy' czy '100% skuteczności'. Bez oceniania ciała "
    "klienta.\n\n"
    "Odpowiadasz WYŁĄCZNIE tablicą JSON, bez markdown, bez komentarzy."
)

USER_TEMPLATE = (
    "USŁUGA: {service}\n"
    "BRANŻA: {vertical}\n"
    "JĘZYK: {language}\n"
    "PROBLEMY KLIENTÓW:\n{problems}\n\n"
    "KĄTY (angle) i liczba hooków na każdy:\n{angles}\n\n"
    "POWIERZCHNIE (surface) i limity znaków:\n{surfaces}\n\n"
    "Dla każdego kąta wygeneruj hooki rozłożone na dozwolone powierzchnie. "
    "Nagłówki (HEADLINE) ≤ 30 znaków, opisy (DESCRIPTION) ≤ 90 znaków, "
    "pozostałe ≤ 25 znaków.\n\n"
    "Przykłady:\n"
    '- {{"text": "Cellulit, który nie znika?", "angle": "PAIN", "surface": "HEADLINE"}}\n'
    '- {{"text": "Diety i ćwiczenia nie pomogły?", "angle": "FAILED_ALTERNATIVE", '
    '"surface": "HEADLINE"}}\n\n'
    "ODPOWIEDŹ — wyłącznie tablica JSON:\n"
    '[{{"text": "...", "angle": "PAIN", "surface": "HEADLINE"}}]'
)


def _format_angles(angle_allocation: dict[str, int]) -> str:
    return "\n".join(f"- {angle}: {count}" for angle, count in angle_allocation.items())


def _format_surfaces(surfaces: list[str]) -> str:
    limits = {"HEADLINE": 30, "DESCRIPTION": 90, "SITELINK": 25, "CALLOUT": 25, "SNIPPET": 25}
    return "\n".join(f"- {s}: ≤ {limits.get(s, 25)} znaków" for s in surfaces)


def _format_problems(problems: list[str]) -> str:
    if not problems:
        return "(brak — wywnioskuj z usługi i branży)"
    return "\n".join(f"- {p}" for p in problems)


def render(
    *,
    service: str,
    vertical: str,
    problems: list[str],
    angle_allocation: dict[str, int],
    surfaces: list[str],
    language: str = "pl",
    system_template: str | None = None,
    user_template: str | None = None,
) -> tuple[str, str]:
    system = system_template or SYSTEM_PROMPT
    template = user_template or USER_TEMPLATE
    user = template.format(
        service=service,
        vertical=vertical,
        language=language,
        problems=_format_problems(problems),
        angles=_format_angles(angle_allocation),
        surfaces=_format_surfaces(surfaces),
    )
    return system, user


SEED_CONTENT = json.dumps(
    {"system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE}, ensure_ascii=False
)
