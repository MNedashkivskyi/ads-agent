"""Polish grammar helpers for ad copy.

The placeholder copy needs the locative case (miejscownik) when a city follows
the preposition "w" — "w Warszawie", not "w Warszawa". Polish declension is
irregular, so we keep an explicit map of the major cities (which cover the vast
majority of real users) and fall back to a grammatically-safe apposition
("— {city}") for anything we don't recognise, rather than emit a broken "w
{nominative}".
"""

from __future__ import annotations

__all__ = ["locative_city", "city_location_phrase"]

# Nominative (lower-cased) -> locative form, for "w <locative>".
_LOCATIVE: dict[str, str] = {
    "warszawa": "Warszawie",
    "kraków": "Krakowie",
    "krakow": "Krakowie",
    "łódź": "Łodzi",
    "lodz": "Łodzi",
    "wrocław": "Wrocławiu",
    "wroclaw": "Wrocławiu",
    "poznań": "Poznaniu",
    "poznan": "Poznaniu",
    "gdańsk": "Gdańsku",
    "gdansk": "Gdańsku",
    "szczecin": "Szczecinie",
    "bydgoszcz": "Bydgoszczy",
    "lublin": "Lublinie",
    "białystok": "Białymstoku",
    "bialystok": "Białymstoku",
    "katowice": "Katowicach",
    "gdynia": "Gdyni",
    "częstochowa": "Częstochowie",
    "czestochowa": "Częstochowie",
    "radom": "Radomiu",
    "sosnowiec": "Sosnowcu",
    "toruń": "Toruniu",
    "torun": "Toruniu",
    "kielce": "Kielcach",
    "rzeszów": "Rzeszowie",
    "rzeszow": "Rzeszowie",
    "gliwice": "Gliwicach",
    "zabrze": "Zabrzu",
    "olsztyn": "Olsztynie",
    "bielsko-biała": "Bielsku-Białej",
    "bielsko-biala": "Bielsku-Białej",
    "bytom": "Bytomiu",
    "zielona góra": "Zielonej Górze",
    "zielona gora": "Zielonej Górze",
    "rybnik": "Rybniku",
    "opole": "Opolu",
    "tychy": "Tychach",
    "płock": "Płocku",
    "plock": "Płocku",
    "elbląg": "Elblągu",
    "elblag": "Elblągu",
    "wałbrzych": "Wałbrzychu",
    "walbrzych": "Wałbrzychu",
    "tarnów": "Tarnowie",
    "tarnow": "Tarnowie",
    "chorzów": "Chorzowie",
    "chorzow": "Chorzowie",
    "koszalin": "Koszalinie",
    "kalisz": "Kaliszu",
    "legnica": "Legnicy",
    "słupsk": "Słupsku",
    "slupsk": "Słupsku",
    "nowy sącz": "Nowym Sączu",
    "nowy sacz": "Nowym Sączu",
    "jelenia góra": "Jeleniej Górze",
    "jelenia gora": "Jeleniej Górze",
    "konin": "Koninie",
    "piła": "Pile",
    "pila": "Pile",
    "sopot": "Sopocie",
    "gniezno": "Gnieźnie",
    "płońsk": "Płońsku",
}


def locative_city(name: str) -> str | None:
    """Return the locative (miejscownik) form of *name*, or None if unknown."""
    if not name:
        return None
    return _LOCATIVE.get(name.strip().lower())


def city_location_phrase(name: str) -> str:
    """Return a grammatical location phrase for a headline.

    "Warszawa" -> "w Warszawie" (known city, proper locative)
    "Zakopane" -> "— Zakopane"  (unknown city, safe apposition — never "w Zakopane")
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return ""
    loc = _LOCATIVE.get(cleaned.lower())
    if loc:
        return f"w {loc}"
    return f"— {cleaned}"
