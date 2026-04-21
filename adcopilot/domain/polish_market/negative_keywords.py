"""Polish negative keyword lists organized by standard category and vertical."""

from __future__ import annotations

# Standard negative categories — each campaign must cover all of these.
# Format: (category_label, list_of_acceptable_terms)
POLISH_STANDARD_NEGATIVES: list[tuple[str, list[str]]] = [
    ("darmowy", ["darmowy", "za darmo", "bezpłatnie", "gratis", "darmowe", "free"]),
    ("praca", ["praca", "oferty pracy", "zarobki", "kariera", "rekrutacja", "stanowisko", "job", "hiring"]),
    ("diy", ["jak zrobić", "samodzielnie", "poradnik", "krok po kroku", "instrukcja", "zrób sam", "diy"]),
    ("edukacja", ["kurs", "szkolenie", "studia", "uczelnia", "egzamin", "tutorial", "how to"]),
    ("forum/media", ["youtube", "tiktok", "forum", "blog", "opinia", "recenzja", "review"]),
]

# Vertical-specific Polish negative keyword lists.
VERTICAL_NEGATIVES_PL: dict[str, list[str]] = {
    "salon": [
        "peruka", "przedłużanie włosów", "farba do włosów sklep",
        "youtube", "tiktok", "diy koloryzacja", "domowe farbowanie",
        "szampon tanio", "odżywka sklep",
    ],
    "prawnik": [
        "prawo karne studia", "aplikacja radcowska", "egzamin adwokacki",
        "wzory pism", "darmowe porady", "wzór umowy", "formularz sądowy",
        "studia prawnicze", "paralegalne",
    ],
    "restauracja": [
        "przepis", "jak ugotować", "kurs gotowania", "dieta",
        "kalorie", "gotowanie w domu", "przepisy kulinarne",
        "blog kulinarny", "kuchnia domowa",
    ],
    "lekarz": [
        "domowe sposoby", "samoleczenie", "studia medyczne", "rezydencja",
        "leki bez recepty sklep", "ziołowe leczenie", "medycyna alternatywna",
        "diagnoza online", "symptomy sprawdź",
    ],
    "ecommerce": [
        "używane", "second hand", "za darmo", "crack", "torrent",
        "nielegalne", "podróbka", "fake", "allegro używane",
    ],
    "nieruchomości": [
        "wynajem studencki", "akademik", "umowa najmu wzór",
        "jak napisać umowę", "podatek od nieruchomości kalkulator",
        "prawo budowlane studia", "architekt studia",
    ],
    "edukacja": [
        "darmowy kurs", "piracki materiał", "crack oprogramowanie",
        "ściągi", "gotowe zadania", "praca domowa rozwiązania",
        "ebook za darmo",
    ],
    "usługi domowe": [
        "jak naprawić samodzielnie", "diy remont", "poradnik hydrauliczny",
        "instrukcja montażu", "youtube naprawy", "sklep z narzędziami",
        "materiały budowlane tanio",
    ],
}
