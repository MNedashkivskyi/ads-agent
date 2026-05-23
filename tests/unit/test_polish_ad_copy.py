"""Tests for Polish ad copy rules and template character limits."""

from __future__ import annotations

import pytest

from adcopilot.domain.launch.templates import _TEMPLATES
from adcopilot.domain.polish_market.ad_copy_rules import (
    DESCRIPTION_MAX_CHARS,
    HEADLINE_MAX_CHARS,
    POLISH_CTA_VERBS,
    POLISH_CTAS,
    description_ok,
    headline_ok,
)

# ---------------------------------------------------------------------------
# ad_copy_rules unit tests
# ---------------------------------------------------------------------------


def test_headline_ok_within_limit() -> None:
    assert headline_ok("Kup Teraz – Sprawdź Ofertę") is True


def test_headline_ok_exactly_30_chars() -> None:
    assert headline_ok("A" * 30) is True


def test_headline_too_long() -> None:
    assert headline_ok("A" * 31) is False


def test_description_ok_within_limit() -> None:
    assert description_ok("Skontaktuj się z nami i uzyskaj darmową wycenę już dziś.") is True


def test_description_ok_exactly_90_chars() -> None:
    assert description_ok("A" * 90) is True


def test_description_too_long() -> None:
    assert description_ok("A" * 91) is False


def test_polish_ctas_dict_has_all_actions() -> None:
    expected_keys = {"Call", "Book", "Purchase", "Visit website", "Sign up", "Contact", "Get offer"}
    assert set(POLISH_CTAS.keys()) == expected_keys


def test_polish_cta_verbs_flat_list_non_empty() -> None:
    assert len(POLISH_CTA_VERBS) > 0


def test_polish_cta_verbs_all_lowercase() -> None:
    for verb in POLISH_CTA_VERBS:
        assert verb == verb.lower(), f"Expected lowercase: {verb!r}"


def test_polish_cta_verbs_contains_key_phrases() -> None:
    assert "zadzwoń teraz" in POLISH_CTA_VERBS
    assert "kup teraz" in POLISH_CTA_VERBS
    assert "zarezerwuj" in POLISH_CTA_VERBS


# ---------------------------------------------------------------------------
# Template character limit validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vertical,template", list(_TEMPLATES.items()))
def test_template_headlines_within_limit(vertical: str, template) -> None:
    for ag in template.ad_groups:
        for ad in ag.ads:
            for hl in ad.headlines:
                assert len(hl) <= HEADLINE_MAX_CHARS, (
                    f"[{vertical}] headline too long ({len(hl)} chars): {hl!r}"
                )


@pytest.mark.parametrize("vertical,template", list(_TEMPLATES.items()))
def test_template_descriptions_within_limit(vertical: str, template) -> None:
    for ag in template.ad_groups:
        for ad in ag.ads:
            for desc in ad.descriptions:
                assert len(desc) <= DESCRIPTION_MAX_CHARS, (
                    f"[{vertical}] description too long ({len(desc)} chars): {desc!r}"
                )
