"""Tests for Polish vertical detection from business descriptions."""

from __future__ import annotations

import pytest

from adcopilot.domain.launch.templates import detect_vertical_from_description


@pytest.mark.parametrize("desc,expected", [
    # Salon — Polish
    ("Salon fryzjerski w centrum Warszawy", "salon"),
    ("Kosmetyczka oferuje zabiegi na twarz i paznokcie", "salon"),
    # Restaurant — Polish
    ("Restauracja włoska z dowozem", "restaurant"),
    ("Kawiarnia i bistro w centrum miasta", "restaurant"),
    # Legal — Polish
    ("Kancelaria adwokacka specjalizująca się w prawie rodzinnym", "legal"),
    ("Prawnik i radca prawny – porady prawne", "legal"),
    # Medical — Polish
    ("Gabinet stomatologiczny – dentysta dla całej rodziny", "medical"),
    ("Przychodnia lekarska i fizjoterapia", "medical"),
    # Ecommerce — Polish
    ("Sklep internetowy z elektroniką, szybka wysyłka", "ecommerce"),
    ("E-sklep – zamów online z dostawą do domu", "ecommerce"),
    # Nieruchomości — Polish
    ("Biuro nieruchomości – mieszkania na wynajem i sprzedaż", "nieruchomości"),
    ("Wynajem i sprzedaż mieszkań w Krakowie", "nieruchomości"),
    # Edukacja — Polish
    ("Korepetycje z matematyki i fizyki dla uczniów", "edukacja"),
    ("Szkolenie zawodowe i kursy online", "edukacja"),
    # Usługi domowe — Polish
    ("Hydraulik – naprawy i instalacje", "usługi domowe"),
    ("Sprzątanie biur i mieszkań, remont", "usługi domowe"),
    # English still works
    ("Hair salon and barber shop", "salon"),
    ("Law firm specialising in corporate law", "legal"),
    ("Online store with fast delivery", "ecommerce"),
    # Unknown → generic
    ("Random unmatchable business description xyz", "generic"),
])
def test_vertical_detection(desc: str, expected: str) -> None:
    result = detect_vertical_from_description(desc)
    assert result == expected, f"Description: {desc!r} → got {result!r}, expected {expected!r}"
