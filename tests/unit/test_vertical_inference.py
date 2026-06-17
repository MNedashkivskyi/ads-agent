"""Unit tests for infer_vertical (Audit Funnel follow-up)."""

from __future__ import annotations

from adcopilot.application.audit.vertical_inference import infer_vertical


def test_infers_vertical_from_signal_words() -> None:
    assert infer_vertical(["Kampania - fryzjer Warszawa", "manicure hybrydowy"]) == "salon"
    assert infer_vertical(["kancelaria adwokat", "porada prawna rozwód"]) == "prawnik"
    assert infer_vertical(["sklep online", "promocja wysyłka"]) == "e-commerce"


def test_returns_none_without_clear_signal() -> None:
    assert infer_vertical(["generic brand campaign", "buy now"]) is None


def test_returns_none_on_empty_input() -> None:
    assert infer_vertical([]) is None
    assert infer_vertical(["", "   "]) is None


def test_picks_the_strongest_signal() -> None:
    # More restaurant signals than salon signals → restauracja wins.
    texts = ["restauracja menu", "pizza dowóz jedzenia", "catering", "salon"]
    assert infer_vertical(texts) == "restauracja"
