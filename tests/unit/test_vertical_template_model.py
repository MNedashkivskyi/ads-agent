"""Unit tests for VerticalTemplate domain entities (Task 1.1)."""

import pytest
from pydantic import ValidationError

from adcopilot.domain.launch.vertical_template import (
    BudgetTierBiddingConfig,
    CompetitiveLevel,
    KeywordEntry,
    KeywordPriority,
    SitelinkTemplate,
    TemplateAdGroup,
    TemplateBiddingDefaults,
    TemplateExtensionDefaults,
    TemplateMatchType,
    TemplateNegativeList,
    VerticalSummary,
    VerticalTemplate,
)


def _make_bidding_defaults() -> TemplateBiddingDefaults:
    cfg = BudgetTierBiddingConfig(
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        max_cpc_limit_pln=5.0,
        daily_budget_ratio=0.9,
    )
    return TemplateBiddingDefaults(micro=cfg, mid=cfg, growth=cfg)


def _make_ad_group(name: str = "Test Group") -> TemplateAdGroup:
    return TemplateAdGroup(
        name_template=name,
        keyword_bank=[
            KeywordEntry(
                text="manicure {city}",
                match_type=TemplateMatchType.PHRASE,
                priority=KeywordPriority.CORE,
            ),
            KeywordEntry(
                text="paznokcie {city}",
                match_type=TemplateMatchType.EXACT,
                priority=KeywordPriority.CORE,
            ),
            KeywordEntry(
                text="salon urody",
                match_type=TemplateMatchType.BROAD,
                priority=KeywordPriority.EXTENDED,
            ),
        ],
    )


def _make_template(vertical_id: str = "beauty_salon") -> VerticalTemplate:
    return VerticalTemplate(
        vertical_id=vertical_id,
        display_name="Salon urody",
        display_emoji="💅",
        language="pl",
        competitive_level=CompetitiveLevel.MEDIUM,
        ad_groups=[_make_ad_group("Manicure i pedicure"), _make_ad_group("Stylizacja paznokci")],
        negatives=TemplateNegativeList(
            universal=["darmowy", "praca", "kurs", "szkolenie", "jak zrobić"],
            vertical_specific=["szkolenie fryzjerskie", "kurs kosmetyczny"],
        ),
        bidding_defaults=_make_bidding_defaults(),
        extensions=TemplateExtensionDefaults(
            sitelinks=[SitelinkTemplate(text="Cennik", path="cennik")],
            callouts=["Szybka wizyta", "Doświadczony personel"],
            structured_snippet_category="Usługi",
        ),
        common_services=["Manicure", "Pedicure", "Stylizacja rzęs", "Mezoterapia"],
    )


class TestKeywordEntry:
    def test_valid_keyword(self):
        kw = KeywordEntry(text="salon beauty {city}", match_type=TemplateMatchType.PHRASE)
        assert kw.priority == KeywordPriority.CORE

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            KeywordEntry(text="", match_type=TemplateMatchType.EXACT)

    def test_invalid_match_type_rejected(self):
        with pytest.raises(ValidationError):
            KeywordEntry(text="test", match_type="INVALID")  # type: ignore[arg-type]


class TestTemplateAdGroup:
    def test_valid_ad_group(self):
        ag = _make_ad_group()
        assert len(ag.keyword_bank) == 3

    def test_empty_keyword_bank_rejected(self):
        with pytest.raises(ValidationError):
            TemplateAdGroup(name_template="Group", keyword_bank=[])

    def test_default_bid_modifier(self):
        ag = _make_ad_group()
        assert ag.default_bid_modifier == 1.0


class TestTemplateNegativeList:
    def test_all_negatives_combines_lists(self):
        neg = TemplateNegativeList(
            universal=["darmowy", "praca"],
            vertical_specific=["kurs fryzjerski"],
        )
        assert neg.all_negatives == ["darmowy", "praca", "kurs fryzjerski"]

    def test_empty_lists_ok(self):
        neg = TemplateNegativeList()
        assert neg.all_negatives == []


class TestTemplateBiddingDefaults:
    def test_for_tier_returns_correct_config(self):
        defaults = _make_bidding_defaults()
        cfg = defaults.for_tier("micro")
        assert cfg.bidding_strategy == "MAXIMIZE_CONVERSIONS"

    def test_daily_budget_ratio_must_be_positive(self):
        with pytest.raises(ValidationError):
            BudgetTierBiddingConfig(
                bidding_strategy="MAXIMIZE_CLICKS",
                max_cpc_limit_pln=2.0,
                daily_budget_ratio=0,
            )

    def test_daily_budget_ratio_must_be_at_most_one(self):
        with pytest.raises(ValidationError):
            BudgetTierBiddingConfig(
                bidding_strategy="MAXIMIZE_CLICKS",
                max_cpc_limit_pln=2.0,
                daily_budget_ratio=1.1,
            )


class TestVerticalTemplate:
    def test_construct_full_template(self):
        tmpl = _make_template()
        assert tmpl.vertical_id == "beauty_salon"
        assert tmpl.language == "pl"
        assert len(tmpl.ad_groups) == 2
        assert len(tmpl.common_services) == 4

    def test_to_summary(self):
        tmpl = _make_template()
        summary: VerticalSummary = tmpl.to_summary()
        assert summary.vertical_id == "beauty_salon"
        assert summary.display_emoji == "💅"

    def test_no_ad_groups_rejected(self):
        with pytest.raises(ValidationError):
            VerticalTemplate(
                vertical_id="test",
                display_name="Test",
                ad_groups=[],
                bidding_defaults=_make_bidding_defaults(),
            )

    def test_competitive_level_enum(self):
        tmpl = _make_template()
        assert tmpl.competitive_level == CompetitiveLevel.MEDIUM

    def test_invalid_competitive_level_rejected(self):
        with pytest.raises(ValidationError):
            VerticalTemplate(
                vertical_id="test",
                display_name="Test",
                competitive_level="ultra",  # type: ignore[arg-type]
                ad_groups=[_make_ad_group()],
                bidding_defaults=_make_bidding_defaults(),
            )
