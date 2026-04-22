"""Tests for account vertical classification use case."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from adcopilot.application.use_cases.classify_account_vertical import (
    ClassifyAccountVerticalUseCase,
    _detect_from_keywords,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import KeywordSnapshot, SnapshotId


def _kw(text: str) -> KeywordSnapshot:
    return KeywordSnapshot(
        id=SnapshotId(str(uuid4())),
        account_id=AccountId("123"),
        snapshot_date=date.today(),
        criterion_id=1,
        ad_group_id=1,
        text=text,
        match_type="PHRASE",
        status="ENABLED",
        quality_score=7,
        impressions=100,
        clicks=10,
        cost_micros=5_000_000,
        conversions=1.0,
        ctr=0.1,
        avg_cpc_micros=500_000,
    )


# ---------------------------------------------------------------------------
# Keyword-based detection
# ---------------------------------------------------------------------------


def test_detect_from_keywords_salon() -> None:
    kws = [_kw("fryzjer warszawa"), _kw("salon fryzjerski"), _kw("kosmetyczka")]
    assert _detect_from_keywords(kws) == "salon"


def test_detect_from_keywords_legal() -> None:
    kws = [_kw("kancelaria prawna"), _kw("adwokat warszawa"), _kw("radca prawny")]
    assert _detect_from_keywords(kws) == "legal"


def test_detect_from_keywords_medical() -> None:
    kws = [_kw("dentysta kraków"), _kw("gabinet stomatologiczny"), _kw("lekarz")]
    assert _detect_from_keywords(kws) == "medical"


def test_detect_from_keywords_ecommerce() -> None:
    kws = [_kw("sklep internetowy"), _kw("e-sklep"), _kw("dostawa")]
    assert _detect_from_keywords(kws) == "ecommerce"


def test_detect_from_keywords_restaurant() -> None:
    kws = [_kw("restauracja włoska"), _kw("kawiarnia"), _kw("catering")]
    assert _detect_from_keywords(kws) == "restaurant"


def test_detect_from_keywords_uslugi_domowe() -> None:
    kws = [_kw("hydraulik warszawa"), _kw("elektryk"), _kw("remont mieszkania")]
    assert _detect_from_keywords(kws) == "usługi domowe"


def test_detect_from_keywords_nieruchomosci() -> None:
    kws = [_kw("biuro nieruchomości"), _kw("wynajem mieszkań"), _kw("sprzedaż mieszkań")]
    assert _detect_from_keywords(kws) == "nieruchomości"


def test_detect_from_keywords_edukacja() -> None:
    kws = [_kw("korepetycje matematyka"), _kw("szkolenie zawodowe"), _kw("kurs online")]
    assert _detect_from_keywords(kws) == "edukacja"


def test_detect_from_empty_keywords_returns_none() -> None:
    assert _detect_from_keywords([]) is None


# ---------------------------------------------------------------------------
# Use case tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_use_case_prefers_business_description() -> None:
    mock_repo = MagicMock()
    mock_repo.update_vertical = AsyncMock()
    uc = ClassifyAccountVerticalUseCase(account_repo=mock_repo)

    # Description says "salon", keywords say nothing
    result = await uc.run(
        account_id="acct-1",
        keywords=[],
        business_description="Salon fryzjerski Piękna w centrum Warszawy",
    )
    assert result == "salon"
    mock_repo.update_vertical.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_case_falls_back_to_keywords() -> None:
    mock_repo = MagicMock()
    mock_repo.update_vertical = AsyncMock()
    uc = ClassifyAccountVerticalUseCase(account_repo=mock_repo)

    result = await uc.run(
        account_id="acct-1",
        keywords=[_kw("kancelaria prawna"), _kw("adwokat")],
        business_description="",
    )
    assert result == "legal"


@pytest.mark.asyncio
async def test_use_case_returns_generic_when_no_match() -> None:
    mock_repo = MagicMock()
    mock_repo.update_vertical = AsyncMock()
    uc = ClassifyAccountVerticalUseCase(account_repo=mock_repo)

    result = await uc.run(account_id="acct-1", keywords=[], business_description="")
    assert result == "generic"
