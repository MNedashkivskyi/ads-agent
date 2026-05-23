"""Tests for CreatePMaxCampaignUseCase — Phase 6 Task 6.2."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.ports.campaign_writer import CreatedPMaxResources
from adcopilot.application.ports.google_ads import MerchantCenterLink
from adcopilot.application.use_cases.create_pmax_campaign import (
    CreatePMaxCampaignInput,
    CreatePMaxCampaignUseCase,
    _audience_signal_names,
    _parse_assets,
    _truncate,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt_repo(content: str = "system prompt") -> AsyncMock:
    repo = AsyncMock()
    pv = MagicMock()
    pv.content = content
    repo.get_latest = AsyncMock(return_value=pv)
    return repo


def _make_llm(response: str) -> AsyncMock:
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


def _make_writer(campaign_rn: str = "customers/123/campaigns/456") -> AsyncMock:
    writer = AsyncMock()
    writer.create_pmax_campaign = AsyncMock(
        return_value=CreatedPMaxResources(
            campaign_resource_name=campaign_rn,
            budget_resource_name="customers/123/campaignBudgets/789",
            asset_group_resource_names=["customers/123/assetGroups/111"],
        )
    )
    return writer


def _make_input(**kwargs) -> CreatePMaxCampaignInput:
    defaults = dict(
        customer_id="1234567890",
        refresh_token="rt",
        merchant_center_link=MerchantCenterLink(
            merchant_id=42, account_name="Sklep", status="ENABLED"
        ),
        monthly_budget_pln=1500.0,
        product_focus="all",
        campaign_name="Testowy Sklep",
        final_url="https://sklep.pl",
        vertical="ecommerce",
    )
    defaults.update(kwargs)
    return CreatePMaxCampaignInput(**defaults)


# ---------------------------------------------------------------------------
# Unit tests — _parse_assets
# ---------------------------------------------------------------------------


def test_parse_assets_valid_json():
    raw = json.dumps(
        {
            "headlines": ["Świetne produkty", "Sprawdź ofertę", "Kup teraz taniej"],
            "descriptions": [
                "Szeroki wybór produktów dla całej rodziny.",
                "Zamów teraz i odbierz szybko.",
            ],
        }
    )
    h, d = _parse_assets(raw, "fallback", "https://x.pl")
    assert h == ["Świetne produkty", "Sprawdź ofertę", "Kup teraz taniej"]
    assert len(d) == 2


def test_parse_assets_truncates_long_headlines():
    long_headline = "A" * 50
    raw = json.dumps(
        {
            "headlines": [long_headline, "B" * 50, "C" * 50],
            "descriptions": ["Opis jeden wystarczająco długi tekst.", "Opis dwa."],
        }
    )
    h, d = _parse_assets(raw, "fallback", "https://x.pl")
    assert all(len(hl) <= 30 for hl in h)


def test_parse_assets_fallback_on_invalid_json():
    h, d = _parse_assets("nie jest JSON", "Mój Sklep", "https://sklep.pl")
    assert len(h) == 3
    assert len(d) == 2
    assert all(len(hl) <= 30 for hl in h)
    assert all(len(desc) <= 90 for desc in d)


def test_parse_assets_fallback_on_missing_fields():
    raw = json.dumps({"headlines": ["Tylko jeden nagłówek"]})
    h, d = _parse_assets(raw, "Sklep", "https://sklep.pl")
    assert len(h) == 3
    assert len(d) == 2


def test_truncate():
    assert _truncate("abcde", 3) == "abc"
    assert _truncate("abc", 10) == "abc"


# ---------------------------------------------------------------------------
# Unit tests — _audience_signal_names
# ---------------------------------------------------------------------------


def test_audience_signal_names_ecommerce():
    names = _audience_signal_names("ecommerce", "111")
    assert len(names) > 0
    assert all("customers/111/userInterests/" in n for n in names)


def test_audience_signal_names_unknown_vertical_falls_back_to_ecommerce():
    names = _audience_signal_names("unknown_vertical", "222")
    assert len(names) > 0


# ---------------------------------------------------------------------------
# Use case integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_creates_paused_campaign():
    llm_response = json.dumps(
        {
            "headlines": ["Sklep Testowy", "Odkryj produkty", "Kup taniej dzisiaj"],
            "descriptions": [
                "Szeroki wybór dla każdego klienta.",
                "Szybka dostawa, darmowe zwroty.",
            ],
        }
    )
    llm = _make_llm(llm_response)
    prompt_repo = _make_prompt_repo()
    writer = _make_writer()

    uc = CreatePMaxCampaignUseCase(llm=llm, prompt_repo=prompt_repo, pmax_writer=writer)
    result = await uc.execute(_make_input())

    writer.create_pmax_campaign.assert_awaited_once()
    call_args = writer.create_pmax_campaign.call_args
    proposal = call_args.kwargs["proposal"]

    assert proposal.merchant_center_feed_id == 42
    assert len(proposal.asset_groups) == 1
    ag = proposal.asset_groups[0]
    assert len(ag.headlines) == 3
    assert len(ag.descriptions) == 2
    assert all(len(h) <= 30 for h in ag.headlines)
    assert all(len(d) <= 90 for d in ag.descriptions)
    assert result.campaign_resource_name == "customers/123/campaigns/456"


@pytest.mark.asyncio
async def test_execute_budget_conversion():
    llm = _make_llm(
        json.dumps(
            {
                "headlines": ["H1", "H2", "H3"],
                "descriptions": ["D1 opis długi wystarczająco.", "D2 opis."],
            }
        )
    )
    writer = _make_writer()
    uc = CreatePMaxCampaignUseCase(llm=llm, prompt_repo=_make_prompt_repo(), pmax_writer=writer)
    await uc.execute(_make_input(monthly_budget_pln=3000.0))

    proposal = writer.create_pmax_campaign.call_args.kwargs["proposal"]
    # 3000 / 30 = 100 PLN/day = 100_000_000 micros
    assert proposal.daily_budget_micros == 100_000_000


@pytest.mark.asyncio
async def test_execute_raises_when_prompt_missing():
    llm = _make_llm("{}")
    prompt_repo = AsyncMock()
    prompt_repo.get_latest = AsyncMock(return_value=None)
    writer = _make_writer()

    uc = CreatePMaxCampaignUseCase(llm=llm, prompt_repo=prompt_repo, pmax_writer=writer)
    with pytest.raises(RuntimeError, match="pmax_asset_generation_v1"):
        await uc.execute(_make_input())


@pytest.mark.asyncio
async def test_execute_audience_signals_set():
    llm = _make_llm(
        json.dumps(
            {
                "headlines": ["Sklep", "Oferta", "Kup teraz"],
                "descriptions": ["Opis produktów w sklepie.", "Zamów teraz."],
            }
        )
    )
    writer = _make_writer()
    uc = CreatePMaxCampaignUseCase(llm=llm, prompt_repo=_make_prompt_repo(), pmax_writer=writer)
    await uc.execute(_make_input(vertical="ecommerce", customer_id="999"))

    proposal = writer.create_pmax_campaign.call_args.kwargs["proposal"]
    assert len(proposal.audience_signals) > 0
    assert all("customers/999" in s for s in proposal.audience_signals)
