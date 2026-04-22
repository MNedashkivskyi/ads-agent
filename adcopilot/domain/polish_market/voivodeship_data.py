"""Voivodeship-level economic data for the Polish market.

Purchasing power indices are relative to the national average (1.0),
based on GUS (Central Statistical Office) GDP per capita data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoivodeshipData:
    name: str
    purchasing_power_index: float


# All 16 Polish voivodeships with purchasing power indices (GUS data).
VOIVODESHIPS: dict[str, VoivodeshipData] = {
    "mazowieckie": VoivodeshipData("mazowieckie", 1.50),
    "dolnośląskie": VoivodeshipData("dolnośląskie", 1.10),
    "wielkopolskie": VoivodeshipData("wielkopolskie", 1.08),
    "pomorskie": VoivodeshipData("pomorskie", 1.05),
    "śląskie": VoivodeshipData("śląskie", 1.02),
    "małopolskie": VoivodeshipData("małopolskie", 0.95),
    "łódzkie": VoivodeshipData("łódzkie", 0.92),
    "zachodniopomorskie": VoivodeshipData("zachodniopomorskie", 0.90),
    "kujawsko-pomorskie": VoivodeshipData("kujawsko-pomorskie", 0.85),
    "lubuskie": VoivodeshipData("lubuskie", 0.85),
    "opolskie": VoivodeshipData("opolskie", 0.83),
    "świętokrzyskie": VoivodeshipData("świętokrzyskie", 0.80),
    "warmińsko-mazurskie": VoivodeshipData("warmińsko-mazurskie", 0.78),
    "podlaskie": VoivodeshipData("podlaskie", 0.77),
    "lubelskie": VoivodeshipData("lubelskie", 0.75),
    "podkarpackie": VoivodeshipData("podkarpackie", 0.70),
}

# City → voivodeship mapping (normalized lowercase, no diacritics alternatives included)
_CITY_TO_VOIVODESHIP: dict[str, str] = {
    # Mazowieckie
    "warszawa": "mazowieckie",
    "warsaw": "mazowieckie",
    "radom": "mazowieckie",
    "płock": "mazowieckie",
    "plock": "mazowieckie",
    "siedlce": "mazowieckie",
    "pruszków": "mazowieckie",
    "pruszkow": "mazowieckie",
    # Dolnośląskie
    "wrocław": "dolnośląskie",
    "wroclaw": "dolnośląskie",
    "legnica": "dolnośląskie",
    "wałbrzych": "dolnośląskie",
    "walbrzych": "dolnośląskie",
    "jelenia góra": "dolnośląskie",
    "jelenia gora": "dolnośląskie",
    # Wielkopolskie
    "poznań": "wielkopolskie",
    "poznan": "wielkopolskie",
    "kalisz": "wielkopolskie",
    "konin": "wielkopolskie",
    "leszno": "wielkopolskie",
    "gniezno": "wielkopolskie",
    # Pomorskie
    "gdańsk": "pomorskie",
    "gdansk": "pomorskie",
    "gdynia": "pomorskie",
    "sopot": "pomorskie",
    "słupsk": "pomorskie",
    "slupsk": "pomorskie",
    "trójmiasto": "pomorskie",
    "trojmiasto": "pomorskie",
    # Śląskie
    "katowice": "śląskie",
    "częstochowa": "śląskie",
    "czestochowa": "śląskie",
    "sosnowiec": "śląskie",
    "gliwice": "śląskie",
    "zabrze": "śląskie",
    "bytom": "śląskie",
    "rybnik": "śląskie",
    "tychy": "śląskie",
    "dąbrowa górnicza": "śląskie",
    "dabrowa gornicza": "śląskie",
    # Małopolskie
    "kraków": "małopolskie",
    "krakow": "małopolskie",
    "tarnów": "małopolskie",
    "tarnow": "małopolskie",
    "nowy sącz": "małopolskie",
    "nowy sacz": "małopolskie",
    "oświęcim": "małopolskie",
    "oswiecim": "małopolskie",
    # Łódzkie
    "łódź": "łódzkie",
    "lodz": "łódzkie",
    "piotrków trybunalski": "łódzkie",
    "piotrkow trybunalski": "łódzkie",
    "tomaszów mazowiecki": "łódzkie",
    "tomaszow mazowiecki": "łódzkie",
    "skierniewice": "łódzkie",
    # Zachodniopomorskie
    "szczecin": "zachodniopomorskie",
    "koszalin": "zachodniopomorskie",
    "stargard": "zachodniopomorskie",
    "kołobrzeg": "zachodniopomorskie",
    "kolobrzeg": "zachodniopomorskie",
    # Kujawsko-Pomorskie
    "bydgoszcz": "kujawsko-pomorskie",
    "toruń": "kujawsko-pomorskie",
    "torun": "kujawsko-pomorskie",
    "włocławek": "kujawsko-pomorskie",
    "wloclawek": "kujawsko-pomorskie",
    "grudziądz": "kujawsko-pomorskie",
    "grudziadz": "kujawsko-pomorskie",
    # Lubuskie
    "zielona góra": "lubuskie",
    "zielona gora": "lubuskie",
    "gorzów wielkopolski": "lubuskie",
    "gorzow wielkopolski": "lubuskie",
    # Opolskie
    "opole": "opolskie",
    "kędzierzyn-koźle": "opolskie",
    "kedzierzyn-kozle": "opolskie",
    "nysa": "opolskie",
    # Świętokrzyskie
    "kielce": "świętokrzyskie",
    "ostrowiec świętokrzyski": "świętokrzyskie",
    "ostrowiec swietokrzyski": "świętokrzyskie",
    "starachowice": "świętokrzyskie",
    # Warmińsko-Mazurskie
    "olsztyn": "warmińsko-mazurskie",
    "elbląg": "warmińsko-mazurskie",
    "elblag": "warmińsko-mazurskie",
    "ełk": "warmińsko-mazurskie",
    "elk": "warmińsko-mazurskie",
    # Podlaskie
    "białystok": "podlaskie",
    "bialystok": "podlaskie",
    "suwałki": "podlaskie",
    "suwalki": "podlaskie",
    "łomża": "podlaskie",
    "lomza": "podlaskie",
    # Lubelskie
    "lublin": "lubelskie",
    "zamość": "lubelskie",
    "zamosc": "lubelskie",
    "chełm": "lubelskie",
    "chelm": "lubelskie",
    "biała podlaska": "lubelskie",
    "biala podlaska": "lubelskie",
    # Podkarpackie
    "rzeszów": "podkarpackie",
    "rzeszow": "podkarpackie",
    "przemyśl": "podkarpackie",
    "przemysl": "podkarpackie",
    "stalowa wola": "podkarpackie",
    "mielec": "podkarpackie",
    "tarnobrzeg": "podkarpackie",
}


def get_voivodeship_for_city(city: str) -> str | None:
    """Return voivodeship name for a known Polish city, or None."""
    return _CITY_TO_VOIVODESHIP.get(city.strip().lower())


def get_purchasing_power_index(voivodeship: str) -> float:
    """Return purchasing power index (relative to national avg = 1.0) for a voivodeship.

    Returns 1.0 for unknown voivodeships.
    """
    data = VOIVODESHIPS.get(voivodeship.strip().lower())
    return data.purchasing_power_index if data else 1.0


def get_purchasing_power_for_city(city: str) -> float:
    """Return purchasing power index for a city; defaults to 1.0 if city is unknown."""
    voivodeship = get_voivodeship_for_city(city)
    if voivodeship is None:
        return 1.0
    return get_purchasing_power_index(voivodeship)
