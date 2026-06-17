"""Versioned "how we calculate this" methodology for the free audit (T1.8).

The version pins exactly what logic produced a given ``WasteReport`` (stored on
the report), and the structured Polish content is what the public report page
renders under "Jak to liczymy". Bump ``METHODOLOGY_VERSION`` whenever the
calculation in ``waste_engine`` changes in a way that affects the numbers.
"""

from __future__ import annotations

METHODOLOGY_VERSION = "1"

METHODOLOGY: dict[str, object] = {
    "version": METHODOLOGY_VERSION,
    "title": "Jak liczymy zmarnowany budżet",
    "summary": (
        "Liczymy konserwatywnie i pokazujemy dowody dla każdej złotówki. "
        "W nagłówku raportu jest tylko potwierdzone marnowanie; szacowane "
        "przepłaty i problemy bez kwoty pokazujemy osobno."
    ),
    "tiers": [
        {
            "key": "confirmed",
            "label": "Potwierdzone marnowanie",
            "in_headline": True,
            "desc": (
                "Pieniądze wydane bez żadnej konwersji: frazy z realnym ruchem i zerem "
                "konwersji (w tym te do zablokowania minus-słowami) oraz słowa kluczowe "
                "bez konwersji."
            ),
        },
        {
            "key": "estimated",
            "label": "Szacowane przepłaty",
            "in_headline": False,
            "desc": (
                "Zawyżone CPC przy niskim Quality Score względem benchmarku dla Twojej "
                "branży i miasta. Oznaczone jako szacunkowe."
            ),
        },
        {
            "key": "qualitative",
            "label": "Problemy bez kwoty",
            "in_headline": False,
            "desc": (
                "Luka w pomiarze konwersji oraz inne wykryte problemy, których nie "
                "wyceniamy w złotówkach."
            ),
        },
    ],
    "guardrails": [
        "Frazę liczymy dopiero przy realnym ruchu (próg kliknięć), nigdy przy pojedynczych kliknięciach.",
        "Kwoty marnowania zaokrąglamy w dół do 10 zł.",
        "Bez benchmarku liczymy tylko frazy o intencji śmieciowej — nigdy nie zmyślamy liczby.",
        "Przy zbyt małej ilości danych pokazujemy stan „za mało danych”, a nie wymyśloną kwotę.",
        "Marnowanie na frazach i słowach kluczowych odejmujemy, aby nie liczyć go podwójnie.",
    ],
}
