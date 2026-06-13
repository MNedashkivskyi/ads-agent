"""Hook judge prompt — score hooks on what makes them convert, reward bold.

Scores each hook 0..1 on four axes: specificity (concrete vs vague), tension
(does it create a gap the reader wants closed?), pain-truth (does it ring true to
the customer's real problem?), and clarity (instantly understandable). Generic,
product-anchored hooks score low; bold, state-anchored hooks score high.
"""

from __future__ import annotations

import json

HOOK_JUDGE_PROMPT_KEY = "cie_hook_judge_v1"

SYSTEM_PROMPT = (
    "Jesteś surowym jurorem reklam. Oceniasz hooki Google Ads dla polskich MŚP. "
    "Nagradzaj odważne, konkretne, zakotwiczone w problemie klienta — karz "
    "ogólniki i sformułowania zakotwiczone w produkcie. Dla każdego hooka podaj "
    "cztery oceny w zakresie 0..1: specificity (konkret), tension (napięcie), "
    "pain_truth (prawda o bólu), clarity (jasność).\n\n"
    "Odpowiadasz WYŁĄCZNIE tablicą JSON, bez markdown, bez komentarzy."
)

USER_TEMPLATE = (
    "USŁUGA: {service}\nBRANŻA: {vertical}\n\n"
    "Oceń każdy hook (zachowaj dokładny tekst w polu 'text'):\n{hooks}\n\n"
    "ODPOWIEDŹ — wyłącznie tablica JSON:\n"
    '[{{"text": "...", "specificity": 0.0, "tension": 0.0, "pain_truth": 0.0, '
    '"clarity": 0.0}}]'
)


def _format_hooks(hooks: list[str]) -> str:
    return "\n".join(f"- {h}" for h in hooks)


def render(
    *,
    hooks: list[str],
    service: str,
    vertical: str,
    system_template: str | None = None,
    user_template: str | None = None,
) -> tuple[str, str]:
    system = system_template or SYSTEM_PROMPT
    template = user_template or USER_TEMPLATE
    user = template.format(service=service, vertical=vertical, hooks=_format_hooks(hooks))
    return system, user


SEED_CONTENT = json.dumps(
    {"system": SYSTEM_PROMPT, "user_template": USER_TEMPLATE}, ensure_ascii=False
)
