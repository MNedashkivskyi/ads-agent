"""Prompt templates and formatting helpers for the recommendation explainer."""

from __future__ import annotations

from adcopilot.domain.recommendation import RecommendationKind

SYSTEM_PROMPT = """
You are an assistant that explains Google Ads recommendations to small business owners.
Rules you MUST follow:
- Write in plain language, no PPC or marketing jargon
- Always lead with the money impact in the user's currency (use the provided savings figure)
- Maximum 4 sentences total
- End with exactly one sentence starting with "If you approve this:"
- Write in the language specified in the user message
- Do NOT invent new actions — only explain the action provided to you
"""

TEMPLATES: dict[RecommendationKind, dict[str, str]] = {
    RecommendationKind.ADD_NEGATIVE_KEYWORD: {
        "pl": (
            "Twoja reklama wyświetliła się na frazę '{search_term}', która wygenerowała"
            " {clicks} kliknięć za {cost} i 0 konwersji. To typowe słowo niezwiązane z Twoją"
            " ofertą. Szacowane oszczędności: {savings}/miesiąc. Możliwe działanie: dodanie"
            " '{search_term}' jako słowa wykluczonego. Wytłumacz jak to działa prostym językiem."
            " Odpowiedz po polsku."
        ),
        "en": (
            "Your ad showed for '{search_term}' which got {clicks} clicks costing {cost} with"
            " 0 conversions. This is likely an irrelevant query. Estimated savings:"
            " {savings}/month. Action: add '{search_term}' as a negative keyword. Explain how"
            " this helps in plain English."
        ),
    },
    RecommendationKind.PAUSE_KEYWORD: {
        "pl": (
            "Słowo kluczowe '{keyword}' wydało {cost} przy {clicks} kliknięciach i 0"
            " konwersjach w ostatnich 30 dniach. Szacowane oszczędności: {savings}/miesiąc."
            " Możliwe działanie: wstrzymanie tego słowa kluczowego. Wytłumacz krótko po polsku."
        ),
        "en": (
            "Keyword '{keyword}' spent {cost} with {clicks} clicks and 0 conversions in the"
            " last 30 days. Estimated savings: {savings}/month. Action: pause this keyword."
            " Explain briefly in plain English."
        ),
    },
    RecommendationKind.PAUSE_AD: {
        "pl": (
            "Reklama wydała {cost} z minimalnym efektem. Szacowane oszczędności:"
            " {savings}/miesiąc. Możliwe działanie: wstrzymanie tej reklamy. Wytłumacz krótko"
            " po polsku."
        ),
        "en": (
            "This ad spent {cost} with minimal results. Estimated savings: {savings}/month."
            " Action: pause this ad. Explain briefly in plain English."
        ),
    },
    RecommendationKind.INCREASE_BUDGET: {
        "pl": (
            "Kampania '{campaign}' osiąga dzienny limit budżetu i ma dobry zwrot z inwestycji"
            " (ROAS: {roas:.1f}x). Sugerowany budżet: {suggested_budget}/dzień (+20%)."
            " Wytłumacz krótko po polsku."
        ),
        "en": (
            "Campaign '{campaign}' is hitting its daily budget limit and has positive ROAS"
            " ({roas:.1f}x). Suggested budget: {suggested_budget}/day (+20%). Explain briefly"
            " in plain English."
        ),
    },
    RecommendationKind.ENABLE_CONVERSION_TRACKING: {
        "pl": (
            "Twoje konto wydaje {cost}/miesiąc na reklamy, ale nie masz skonfigurowanego"
            " śledzenia konwersji. Bez tego nie wiesz, co działa. Wyjaśnij dlaczego to ważne,"
            " po polsku."
        ),
        "en": (
            "Your account is spending {cost}/month on ads but has no conversion tracking"
            " configured. Without it you're flying blind. Explain why this matters in plain"
            " English."
        ),
    },
    RecommendationKind.FIX_DISAPPROVED_AD: {
        "pl": (
            "Reklama ID {ad_id} została odrzucona przez Google i nie wyświetla się. Wymaga"
            " ręcznej poprawki. Wyjaśnij krótko po polsku."
        ),
        "en": (
            "Ad ID {ad_id} has been disapproved by Google and is not showing. It requires"
            " manual review. Explain briefly in plain English."
        ),
    },
    RecommendationKind.CHANGE_MATCH_TYPE: {
        "pl": (
            "Słowo kluczowe '{keyword}' w dopasowaniu szerokim generuje {bleed_pct:.0f}%"
            " ruchu niezwiązanego z Twoją ofertą. Możliwe działanie: zmiana na dopasowanie do"
            " wyrażenia. Wytłumacz krótko po polsku."
        ),
        "en": (
            "Keyword '{keyword}' on broad match is generating {bleed_pct:.0f}% irrelevant"
            " traffic. Action: switch to phrase match. Explain briefly in plain English."
        ),
    },
    RecommendationKind.ADD_AD_VARIATION: {
        "pl": (
            "Grupa reklam '{ad_group}' ma tylko jedną aktywną reklamę i {impressions}"
            " wyświetleń. Dodanie drugiej reklamy pozwoli testować, co lepiej działa."
            " Wytłumacz po polsku."
        ),
        "en": (
            "Ad group '{ad_group}' has only one active ad with {impressions} impressions."
            " Adding a variation enables A/B testing. Explain in plain English."
        ),
    },
    RecommendationKind.ADJUST_BIDDING_STRATEGY: {
        "pl": (
            "Kampania '{campaign}' ma {conversions} konwersji i nadal używa strategii"
            " Maksymalizacja kliknięć. Zmiana na Maksymalizacja konwersji może znacznie"
            " poprawić wyniki. Wytłumacz po polsku."
        ),
        "en": (
            "Campaign '{campaign}' has {conversions} conversions but still uses Maximize"
            " Clicks bidding. Switching to Maximize Conversions could significantly improve"
            " results. Explain in plain English."
        ),
    },
    RecommendationKind.ADJUST_BUDGET: {
        "pl": (
            "Budżet kampanii wymaga korekty. Szacowane oszczędności/zysk: {savings}/miesiąc."
            " Wytłumacz krótko po polsku."
        ),
        "en": (
            "Campaign budget needs adjustment. Estimated savings/gain: {savings}/month."
            " Explain briefly in plain English."
        ),
    },
}


def format_micros_as_currency(micros: int, currency: str = "EUR") -> str:
    """Convert micros to human-readable currency string.

    Examples:
        10_500_000 -> '€10.50'
        1_000_000_000 -> '€1000.00'
    """
    symbols = {"EUR": "€", "USD": "$", "GBP": "£", "PLN": "zł"}
    symbol = symbols.get(currency, currency + " ")
    value = micros / 1_000_000
    if currency == "PLN":
        return f"{value:.2f} {symbol}"
    return f"{symbol}{value:.2f}"
