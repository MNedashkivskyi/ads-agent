"""Tests for Polish budget validator."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adcopilot.domain.polish_market.budget_validator import validate_budget


def test_budget_below_minimum_triggers_warning() -> None:
    result = validate_budget("salon", "Warszawa", Decimal("200"))
    assert result.is_low is True
    assert result.warning_message is not None
    assert "⚠️" in result.warning_message
    assert "salon" in result.warning_message
    assert "Warszawa" in result.warning_message
    assert str(result.min_budget_pln) in result.warning_message


def test_budget_above_minimum_no_warning() -> None:
    result = validate_budget("salon", "Warszawa", Decimal("2000"))
    assert result.is_low is False
    assert result.warning_message is None


def test_unknown_vertical_no_warning() -> None:
    result = validate_budget("unknown_niche", "Warszawa", Decimal("100"))
    assert result.is_low is False
    assert result.warning_message is None
    assert result.min_budget_pln is None


def test_warning_includes_recommended_budget_in_message() -> None:
    result = validate_budget("prawnik", "Warszawa", Decimal("500"))
    assert result.is_low is True
    assert result.recommended_budget_pln is not None
    assert result.recommended_budget_pln > result.min_budget_pln


def test_tier_2_city_different_minimum() -> None:
    tier1 = validate_budget("lekarz", "Warszawa", Decimal("1"))
    tier2 = validate_budget("lekarz", "Gdańsk", Decimal("1"))
    assert tier1.min_budget_pln > tier2.min_budget_pln
