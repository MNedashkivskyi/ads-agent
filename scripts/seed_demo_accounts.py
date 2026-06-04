"""Seed 5–10 synthetic demo businesses with realistic, scenario-rich data.

Why this exists
---------------
The product's brain (detection rules, seasonality, conversion-lag, competitor
scan, reporting, weekly insights, digests, bulk selection) reads from our OWN
Postgres snapshot tables — not live from Google Ads on every call. Google Ads
*test* accounts never serve ads, so they return no metrics and can't exercise
any of that. This script writes the same rows the snapshot pipeline would,
directly into Postgres, so the whole read-side product can be validated against
"real-feeling" data with **no Google Ads account, no spend, no billing**.

Each demo account is a distinct Polish-market business (its own vertical) with
~8 weeks of daily snapshots, and one deliberately-planted scenario so a specific
detection rule has something to fire on:

  salon (Kraków)        — CPA spike         -> rule 12 (HIGH; short lag window)
  prawnik (Warszawa)    — CVR drop          -> rule 13 (downgraded to LOW; 45-day lag)
  lekarz (Poznań)       — low Quality Score -> rules 03/16 + QS plan eligibility
  restauracja (Gdańsk)  — wasted search term-> rule 01 (add negative)
  fitness (Wrocław)     — competitor surge  -> rules new_competitor / aggression
  nieruchomosci (Łódź)  — budget capped     -> rule 07 / IS-lost-to-budget
  e-commerce (Szczecin) — spend acceleration-> rule 15
  edukacja (Lublin)     — healthy control   -> nothing should fire
  auto (Katowice)       — no conv. tracking -> ENABLE_CONVERSION_TRACKING
  fizjoterapia (Bydg.)  — ad fatigue        -> CTR decline / AD_FATIGUE
  sklep (Toruń)         — IS erosion        -> IMPRESSION_SHARE_EROSION

Snapshots also carry seasonality (via the real per-vertical multipliers),
conversion actions, business-economics targets (so actuals-vs-target lights up),
search terms and 14 days of auction insights (competitor scan). Each account
additionally gets account-level negatives, campaign extensions (with deliberate
gaps), device / geo / hour / day-of-week performance breakdowns, one PENDING
recommendation matching its planted scenario, and weekly digest + insight
notifications — so the review queue, bulk-execute, dimension rules, and the
in-app notification feed all light up without first running detection.

Idempotent: demo data is keyed by the ``@demo.local`` user-email marker and the
``[DEMO]`` account-name prefix; ``--reset`` wipes prior demo rows first.

Usage
-----
    # validate generation logic WITHOUT a database (no Postgres needed):
    python scripts/seed_demo_accounts.py --dry-run

    # seed against the configured DATABASE_URL (point it at a NON-prod DB):
    python scripts/seed_demo_accounts.py --reset

    # tune:
    python scripts/seed_demo_accounts.py --reset --days 56 --end-date 2026-06-04

Refuses to run when ENV=production unless --force is given.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import sys
import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adcopilot.domain.polish_market.seasonality import get_seasonal_multiplier  # noqa: E402
from adcopilot.infrastructure.db.models import (  # noqa: E402
    AdGroupSnapshotModel,
    AdSnapshotModel,
    AuctionInsightsSnapshotModel,
    BusinessEconomicsModel,
    CampaignExtensionSnapshotModel,
    CampaignSnapshotModel,
    ConversionActionSnapshotModel,
    DayOfWeekPerformanceSnapshotModel,
    DevicePerformanceSnapshotModel,
    GeoPerformanceSnapshotModel,
    GoogleAdsAccountModel,
    HourPerformanceSnapshotModel,
    KeywordSnapshotModel,
    NegativeKeywordSnapshotModel,
    NotificationModel,
    RecommendationModel,
    SearchTermSnapshotModel,
    UserModel,
)

_PLN = 1_000_000  # micros per PLN
_DEMO_EMAIL_DOMAIN = "demo.local"
_DEMO_NAME_PREFIX = "[DEMO]"


# --------------------------------------------------------------------------- #
# Demo business catalogue
# --------------------------------------------------------------------------- #


DEMO_BUSINESSES = [
    {
        "name": "Salon Piękności Bella",
        "city": "Kraków",
        "vertical": "salon",  # seasonality/lag key
        "scenario": "cpa_spike",
        "target_cpa": 45.0,
        "target_roas": None,
        "aov": 180.0,
        "keywords": [
            "manicure hybrydowy kraków",
            "salon paznokci kraków",
            "stylizacja rzęs kraków",
            "fryzjer damski kraków",
            "pedicure kraków cena",
        ],
        "competitors": ["salonybella.pl", "krakow-uroda.pl"],
    },
    {
        "name": "Kancelaria Nowak i Wspólnicy",
        "city": "Warszawa",
        "vertical": "prawnik",
        "scenario": "cvr_drop",
        "target_cpa": 220.0,
        "target_roas": None,
        "aov": 1500.0,
        "keywords": [
            "adwokat warszawa rozwód",
            "kancelaria prawna warszawa",
            "prawnik spadki warszawa",
            "radca prawny warszawa cena",
            "obsługa prawna firm warszawa",
        ],
        "competitors": ["legalis-kancelaria.pl", "prawnicy-warszawa.pl"],
    },
    {
        "name": "Klinika Dental Plus",
        "city": "Poznań",
        "vertical": "lekarz",
        "scenario": "low_qs",
        "target_cpa": 90.0,
        "target_roas": None,
        "aov": 600.0,
        "keywords": [
            "dentysta poznań implanty",
            "stomatolog poznań cennik",
            "leczenie kanałowe poznań",
            "ortodonta poznań aparat",
            "wybielanie zębów poznań",
        ],
        "competitors": ["dentmed-poznan.pl", "klinika-usmiech.pl"],
    },
    {
        "name": "Restauracja Smak Polski",
        "city": "Gdańsk",
        "vertical": "restauracja",
        "scenario": "wasted_search_term",
        "target_cpa": 25.0,
        "target_roas": None,
        "aov": 120.0,
        "keywords": [
            "restauracja gdańsk rezerwacja",
            "obiady gdańsk dowóz",
            "catering gdańsk wesele",
            "restauracja rybna gdańsk",
            "kolacja gdańsk starówka",
        ],
        "competitors": ["smaki-gdanska.pl", "restauracje-trojmiasto.pl"],
    },
    {
        "name": "FitZone Studio",
        "city": "Wrocław",
        "vertical": "fitness",
        "scenario": "competitor_surge",
        "target_cpa": 60.0,
        "target_roas": None,
        "aov": 200.0,
        "keywords": [
            "siłownia wrocław karnet",
            "trener personalny wrocław",
            "fitness wrocław centrum",
            "zajęcia grupowe wrocław",
            "klub fitness wrocław cena",
        ],
        "competitors": ["fitwroclaw.pl", "silownie-wroclaw.pl"],
    },
    {
        "name": "Nieruchomości Dom i Klucz",
        "city": "Łódź",
        "vertical": "nieruchomosci",
        "scenario": "budget_capped",
        "target_cpa": 150.0,
        "target_roas": None,
        "aov": 4000.0,
        "keywords": [
            "mieszkania na sprzedaż łódź",
            "biuro nieruchomości łódź",
            "domy łódź sprzedaż",
            "wynajem mieszkań łódź",
            "agent nieruchomości łódź",
        ],
        "competitors": ["nieruchomosci-lodz.pl", "domiklucz.pl"],
    },
    {
        "name": "e-Sklep Moda24",
        "city": "Szczecin",
        "vertical": "e-commerce",
        "scenario": "spend_accel",
        "target_cpa": None,
        "target_roas": 4.0,
        "aov": 220.0,
        "keywords": [
            "sukienki wieczorowe sklep",
            "buty damskie online",
            "kurtki zimowe sklep",
            "torebki skórzane sklep",
            "moda damska wyprzedaż",
        ],
        "competitors": ["modaonline.pl", "sklep-ubrania.pl"],
    },
    {
        "name": "Szkoła Językowa LinguaPlus",
        "city": "Lublin",
        "vertical": "edukacja",
        "scenario": "healthy",
        "target_cpa": 70.0,
        "target_roas": None,
        "aov": 900.0,
        "keywords": [
            "kurs angielskiego lublin",
            "szkoła językowa lublin",
            "korepetycje angielski lublin",
            "kurs niemieckiego lublin",
            "angielski dla firm lublin",
        ],
        "competitors": ["jezyki-lublin.pl", "linguaschool.pl"],
    },
    {
        "name": "Auto-Serwis Kowalski",
        "city": "Katowice",
        "vertical": "auto",  # no seasonal profile -> flat multiplier
        "scenario": "no_tracking",
        "target_cpa": 80.0,
        "target_roas": None,
        "aov": 500.0,
        "keywords": [
            "mechanik katowice",
            "wymiana oleju katowice",
            "serwis klimatyzacji katowice",
            "naprawa hamulców katowice",
            "diagnostyka komputerowa katowice",
        ],
        "competitors": ["autoserwis-katowice.pl", "mechanicy-slask.pl"],
    },
    {
        "name": "Centrum Fizjoterapii RehaMed",
        "city": "Bydgoszcz",
        "vertical": "fizjoterapia",  # 14-day attribution window
        "scenario": "ad_fatigue",
        "target_cpa": 65.0,
        "target_roas": None,
        "aov": 250.0,
        "keywords": [
            "fizjoterapeuta bydgoszcz",
            "rehabilitacja bydgoszcz",
            "masaż leczniczy bydgoszcz",
            "fizjoterapia kręgosłupa bydgoszcz",
            "terapia manualna bydgoszcz",
        ],
        "competitors": ["rehabilitacja-bydgoszcz.pl", "fizjomed.pl"],
    },
    {
        "name": "Sklep Zoologiczny ZooŚwiat",
        "city": "Toruń",
        "vertical": "sklep",  # 7-day attribution window
        "scenario": "is_erosion",
        "target_cpa": 35.0,
        "target_roas": None,
        "aov": 140.0,
        "keywords": [
            "karma dla psa toruń",
            "sklep zoologiczny toruń",
            "akcesoria dla kota toruń",
            "akwarystyka toruń",
            "karma dla kota online",
        ],
        "competitors": ["zoo-torun.pl", "sklep-zoologiczny24.pl"],
    },
]


# --------------------------------------------------------------------------- #
# Metric generation
# --------------------------------------------------------------------------- #


def _jitter(rng: random.Random, lo: float = 0.85, hi: float = 1.15) -> float:
    return rng.uniform(lo, hi)


def _campaign_day_metrics(
    rng: random.Random,
    *,
    vertical: str,
    d: date,
    day_index: int,
    base_impr: int,
    base_ctr: float,
    base_cvr: float,
    base_cpc_pln: float,
    aov: float,
) -> dict:
    """One campaign's metrics for a day, with weekday + monthly seasonality, a
    slight growth trend and noise. Sized so daily conversions clear rule minimums."""
    weekday = d.weekday()
    weekday_factor = 0.78 if weekday >= 5 else 1.0  # weekends quieter
    seasonal = get_seasonal_multiplier(vertical, d.month)
    trend = 1.0 + 0.0025 * day_index
    impr = max(1, int(base_impr * weekday_factor * seasonal * trend * _jitter(rng)))
    ctr = base_ctr * _jitter(rng, 0.9, 1.1)
    clicks = max(0, int(impr * ctr))
    cpc_micros = int(base_cpc_pln * _PLN * _jitter(rng, 0.9, 1.1))
    cost_micros = clicks * cpc_micros
    conversions = round(clicks * base_cvr * _jitter(rng), 1)
    conv_value = round(conversions * aov, 2)
    return {
        "impressions": impr,
        "clicks": clicks,
        "cost_micros": cost_micros,
        "conversions": conversions,
        "conv_value": conv_value,
    }


def _build_account(biz: dict, index: int, *, days: int, end_date: date) -> dict:
    """Build all ORM rows for one demo business. Returns {model_name: [rows]}."""
    rng = random.Random(f"demo-{index}-{biz['vertical']}")  # reproducible per account

    account_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"demo-account-{index}")
    user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"demo-user-{index}")
    now = datetime.now(tz=UTC)
    start_date = end_date - timedelta(days=days - 1)

    rows: dict[str, list] = {
        k: []
        for k in (
            "users",
            "accounts",
            "economics",
            "campaigns",
            "ad_groups",
            "keywords",
            "ads",
            "search_terms",
            "conversion_actions",
            "auction_insights",
            "negatives",
            "extensions",
            "device_perf",
            "geo_perf",
            "hour_perf",
            "dow_perf",
            "recommendations",
            "notifications",
        )
    }

    rows["users"].append(
        UserModel(
            id=user_uuid,
            email=f"demo{index}@{_DEMO_EMAIL_DOMAIN}",
            plan="business",
            notifications_paused=False,
            language="pl",
            subscription_status="active",
            created_at=now,
            updated_at=now,
        )
    )
    rows["accounts"].append(
        GoogleAdsAccountModel(
            id=account_uuid,
            user_id=user_uuid,
            customer_id=f"100-555-{1000 + index:04d}",
            descriptive_name=f"{_DEMO_NAME_PREFIX} {biz['name']} ({biz['city']})",
            currency="PLN",
            timezone="Europe/Warsaw",
            is_manager=False,
            write_enabled=True,
            needs_reauth=False,
            connected_at=now,
            vertical=biz["vertical"],
            vertical_classified_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    rows["economics"].append(
        BusinessEconomicsModel(
            account_id=account_uuid,
            target_cpa=biz["target_cpa"],
            target_roas=biz["target_roas"],
            primary_goal="SALES" if biz["target_roas"] else "LEADS",
            avg_order_value=biz["aov"],
            currency_code="PLN",
            brand_terms=[],
            excluded_terms=[],
            updated_at=now,
        )
    )

    campaign_id = 5_000_000 + index * 100
    ad_group_id = 6_000_000 + index * 100
    budget_pln = 120.0  # daily budget
    scenario = biz["scenario"]

    # Per-business metric scale (sized so >=5 conversions/day clears rule minimums).
    base = dict(base_impr=2600, base_ctr=0.06, base_cvr=0.05, base_cpc_pln=3.2, aov=biz["aov"])

    # Conversion action(s) — snapshotted on the latest date (config, not daily metric).
    tracking_status = "HIDDEN" if scenario == "no_tracking" else "ENABLED"
    rows["conversion_actions"].append(
        ConversionActionSnapshotModel(
            id=uuid.uuid4(),
            account_id=account_uuid,
            snapshot_date=end_date,
            conversion_action_id=7_000_000 + index,
            name="Zakup" if biz["target_roas"] else "Kontakt / Zapytanie",
            category="PURCHASE" if biz["target_roas"] else "LEAD",
            counting_type="ONE_PER_CLICK",
            status=tracking_status,
            include_in_conversions_metric=True,
            all_conversions=0.0,
            created_at=now,
            updated_at=now,
        )
    )

    # Ad groups + keywords (config rows snapshotted daily for metric history).
    ad_groups = [("Główne usługi", biz["keywords"][:3]), ("Pozostałe", biz["keywords"][3:])]
    ag_ids: list[int] = [ad_group_id + i for i in range(len(ad_groups))]

    # Daily snapshots
    for day_index in range(days):
        d = start_date + timedelta(days=day_index)
        is_latest = d == end_date
        m = _campaign_day_metrics(rng, vertical=biz["vertical"], d=d, day_index=day_index, **base)

        # Impression share + budget signals
        sis = round(rng.uniform(0.55, 0.8), 3)
        budget_lost = round(rng.uniform(0.02, 0.08), 3)
        rank_lost = round(rng.uniform(0.05, 0.15), 3)

        # ---- scenario injection (latest day = "current" window vs 7-days-ago) ----
        if scenario == "is_erosion":
            # Stable high IS, then a sharp drop on the latest day (clears 15pp).
            sis = 0.35 if is_latest else round(rng.uniform(0.68, 0.74), 3)
        if is_latest and scenario == "cpa_spike":
            # +130% so it clears even the peak-month seasonal threshold (0.50*1.3).
            m["cost_micros"] = int(m["cost_micros"] * 2.3)
        elif is_latest and scenario == "cvr_drop":
            m["conversions"] = round(m["conversions"] * 0.5, 1)  # -50% CVR
        elif is_latest and scenario == "spend_accel":
            m["cost_micros"] = int(m["cost_micros"] * 2.0)  # +100% spend, conv flat
            m["conversions"] = round(m["conversions"] * 0.98, 1)
        elif scenario == "budget_capped":
            m["cost_micros"] = int(budget_pln * _PLN * rng.uniform(0.97, 1.0))
            budget_lost = round(rng.uniform(0.30, 0.45), 3)
            sis = round(rng.uniform(0.35, 0.5), 3)

        rows["campaigns"].append(
            CampaignSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=d,
                campaign_id=campaign_id,
                name=f"{biz['city']} – Search",
                status="ENABLED",
                channel_type="SEARCH",
                budget_micros=int(budget_pln * _PLN),
                bidding_strategy="MAXIMIZE_CONVERSIONS"
                if not biz["target_roas"]
                else "MAXIMIZE_CONVERSION_VALUE",
                impressions=m["impressions"],
                clicks=m["clicks"],
                cost_micros=m["cost_micros"],
                conversions=m["conversions"],
                conv_value=m["conv_value"],
                search_impression_share=sis,
                search_budget_lost_impression_share=budget_lost,
                search_rank_lost_impression_share=rank_lost,
                target_cpa_micros=int(biz["target_cpa"] * _PLN) if biz["target_cpa"] else None,
                all_conversions=m["conversions"],
                created_at=now,
                updated_at=now,
            )
        )

        # Split campaign metrics across the two ad groups
        for ag_offset, (ag_name, kws) in enumerate(ad_groups):
            share = 0.6 if ag_offset == 0 else 0.4
            ag_impr = int(m["impressions"] * share)
            ag_clicks = int(m["clicks"] * share)
            ag_conv = round(m["conversions"] * share, 1)
            ag_cost = int(m["cost_micros"] * share)
            # ad-fatigue style CTR drop on the control? keep simple: stable.
            rows["ad_groups"].append(
                AdGroupSnapshotModel(
                    id=uuid.uuid4(),
                    account_id=account_uuid,
                    snapshot_date=d,
                    ad_group_id=ag_ids[ag_offset],
                    campaign_id=campaign_id,
                    name=ag_name,
                    status="ENABLED",
                    impressions=ag_impr,
                    clicks=ag_clicks,
                    cost_micros=ag_cost,
                    conversions=ag_conv,
                    created_at=now,
                    updated_at=now,
                )
            )

            # One RSA per ad group. Ad-fatigue: CTR drops on the latest day
            # (clicks down ~35%) while impressions stay stable, on the first group.
            ad_clicks = ag_clicks
            if scenario == "ad_fatigue" and is_latest and ag_offset == 0:
                ad_clicks = int(ag_clicks * 0.62)
            rows["ads"].append(
                AdSnapshotModel(
                    id=uuid.uuid4(),
                    account_id=account_uuid,
                    snapshot_date=d,
                    ad_id=8_000_000 + index * 100 + ag_offset,
                    ad_group_id=ag_ids[ag_offset],
                    type="RESPONSIVE_SEARCH_AD",
                    status="ENABLED",
                    headlines_json=json.dumps([f"{biz['name']}", "Sprawdź ofertę", "Umów się"]),
                    descriptions_json=json.dumps(["Profesjonalna obsługa.", "Zadzwoń już dziś."]),
                    final_urls_json=json.dumps([f"https://demo-{index}.example.pl"]),
                    impressions=ag_impr,
                    clicks=ad_clicks,
                    cost_micros=ag_cost,
                    conversions=ag_conv,
                    ad_strength="POOR" if (scenario == "ad_fatigue" and ag_offset == 0) else "GOOD",
                    created_at=now,
                    updated_at=now,
                )
            )

            # Keywords for this ad group (daily snapshot for QS/metric history)
            for k_offset, kw_text in enumerate(kws):
                crit_id = 9_000_000 + index * 1000 + ag_offset * 100 + k_offset
                kw_impr = max(1, int(ag_impr / max(1, len(kws))))
                kw_clicks = max(0, int(ag_clicks / max(1, len(kws))))
                qs = 7
                e_ctr = a_rel = lpe = "AVERAGE"
                if scenario == "low_qs" and ag_offset == 0 and k_offset == 0:
                    qs, e_ctr, a_rel, lpe = 3, "BELOW_AVERAGE", "BELOW_AVERAGE", "AVERAGE"
                rows["keywords"].append(
                    KeywordSnapshotModel(
                        id=uuid.uuid4(),
                        account_id=account_uuid,
                        snapshot_date=d,
                        criterion_id=crit_id,
                        ad_group_id=ag_ids[ag_offset],
                        text=kw_text,
                        match_type="PHRASE",
                        status="ENABLED",
                        quality_score=qs,
                        expected_ctr=e_ctr,
                        ad_relevance=a_rel,
                        landing_page_experience=lpe,
                        impressions=kw_impr,
                        clicks=kw_clicks,
                        cost_micros=int(ag_cost / max(1, len(kws))),
                        conversions=round(ag_conv / max(1, len(kws)), 1),
                        ctr=round(kw_clicks / kw_impr, 4) if kw_impr else 0.0,
                        avg_cpc_micros=int(base["base_cpc_pln"] * _PLN),
                        created_at=now,
                        updated_at=now,
                    )
                )

        # Search terms (last 14 days only, to keep volume bounded)
        if (end_date - d).days < 14:
            st_terms = [(kw, False) for kw in biz["keywords"][:2]]
            if scenario == "wasted_search_term":
                st_terms.append(("darmowy " + biz["keywords"][0].split()[0], True))
            for st_text, wasted in st_terms:
                if wasted:
                    # clicks + spend well past rule_01's floor (>30% of target CPA, ≥5 clicks).
                    st_clicks, st_conv, st_cost = 15, 0.0, int(20.0 * _PLN)
                else:
                    st_clicks = rng.randint(3, 12)
                    st_conv = round(st_clicks * 0.05, 1)
                    st_cost = int(st_clicks * base["base_cpc_pln"] * _PLN)
                rows["search_terms"].append(
                    SearchTermSnapshotModel(
                        id=uuid.uuid4(),
                        account_id=account_uuid,
                        snapshot_date=d,
                        search_term=st_text,
                        ad_group_id=ag_ids[0],
                        impressions=st_clicks * 8,
                        clicks=st_clicks,
                        cost_micros=st_cost,
                        conversions=st_conv,
                        matched_keyword_id=9_000_000 + index * 1000,
                        created_at=now,
                        updated_at=now,
                    )
                )

        # Auction insights (last 14 days): baseline competitors + a surge
        if (end_date - d).days < 14:
            for comp in biz["competitors"]:
                rows["auction_insights"].append(
                    AuctionInsightsSnapshotModel(
                        id=uuid.uuid4(),
                        account_id=account_uuid,
                        campaign_id=campaign_id,
                        competitor_domain=comp,
                        impression_share=round(rng.uniform(0.2, 0.45), 3),
                        overlap_rate=round(rng.uniform(0.3, 0.6), 3),
                        position_above_rate=round(rng.uniform(0.2, 0.5), 3),
                        snapshot_date=d,
                        created_at=now,
                    )
                )
            # competitor surge: a NEW domain appearing only in the last 7 days
            if scenario == "competitor_surge" and (end_date - d).days < 7:
                rows["auction_insights"].append(
                    AuctionInsightsSnapshotModel(
                        id=uuid.uuid4(),
                        account_id=account_uuid,
                        campaign_id=campaign_id,
                        competitor_domain="nowy-rywal.pl",
                        impression_share=round(rng.uniform(0.35, 0.55), 3),
                        overlap_rate=round(rng.uniform(0.5, 0.7), 3),
                        position_above_rate=round(rng.uniform(0.5, 0.7), 3),
                        snapshot_date=d,
                        created_at=now,
                    )
                )

    # ------------------------------------------------------------------ #
    # Point-in-time dimension snapshots (latest date only) + recs/notifs.
    # `m`, `sis`, `budget_lost` still hold the latest day's values here.
    # ------------------------------------------------------------------ #
    latest_impr = m["impressions"]
    latest_clicks = m["clicks"]
    latest_cost = m["cost_micros"]
    latest_conv = m["conversions"]

    # ---- Account-level negative keywords (shared junk terms) ----
    for neg_offset, neg_text in enumerate(("praca", "opinie", "za darmo", "wikipedia")):
        rows["negatives"].append(
            NegativeKeywordSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                criterion_id=4_500_000 + index * 100 + neg_offset,
                campaign_id=campaign_id,
                ad_group_id=0,
                text=neg_text,
                match_type="BROAD",
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Campaign extensions (some scenarios deliberately missing types
    #      so the ADD_SITELINKS / ADD_CALLOUTS / ADD_STRUCTURED_SNIPPETS
    #      rules have a gap to surface). ----
    ext_types = ["SITELINK", "CALLOUT", "STRUCTURED_SNIPPET"]
    if scenario in ("ad_fatigue", "no_tracking"):
        ext_types = ["SITELINK"]  # missing callouts + snippets
    elif scenario == "low_qs":
        ext_types = ["SITELINK", "CALLOUT"]  # missing structured snippets
    for ext_type in ext_types:
        rows["extensions"].append(
            CampaignExtensionSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                campaign_id=campaign_id,
                extension_type=ext_type,
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Device performance (mobile-heavy; mobile underperforms enough
    #      on a couple of accounts to surface a device bid adjustment). ----
    device_split = {"MOBILE": 0.56, "DESKTOP": 0.37, "TABLET": 0.07}
    for device, share in device_split.items():
        # Mobile converts worse than desktop on most accounts.
        conv_factor = 0.7 if device == "MOBILE" else (1.25 if device == "DESKTOP" else 0.9)
        rows["device_perf"].append(
            DevicePerformanceSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                campaign_id=campaign_id,
                device=device,
                impressions=int(latest_impr * share),
                clicks=int(latest_clicks * share),
                cost_micros=int(latest_cost * share),
                conversions=round(latest_conv * share * conv_factor, 1),
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Geo performance (city core vs surrounding region) ----
    geo_split = [(1_000_000 + index, 0.7, 1.15), (2_000_000 + index, 0.3, 0.6)]
    for loc_id, share, conv_factor in geo_split:
        rows["geo_perf"].append(
            GeoPerformanceSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                campaign_id=campaign_id,
                location_id=loc_id,
                impressions=int(latest_impr * share),
                clicks=int(latest_clicks * share),
                cost_micros=int(latest_cost * share),
                conversions=round(latest_conv * share * conv_factor, 1),
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Hour-of-day performance (business-hours peak; late-night waste) ----
    hour_weights = [
        0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.8, 1.2, 1.4, 1.5, 1.4,
        1.3, 1.3, 1.4, 1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.6, 0.4, 0.3,
    ]
    weight_sum = sum(hour_weights)
    for hour, w in enumerate(hour_weights):
        share = w / weight_sum
        # Late-night clicks convert poorly (ad-schedule rule fodder).
        conv_factor = 0.4 if hour in (0, 1, 2, 3, 4) else 1.0
        rows["hour_perf"].append(
            HourPerformanceSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                campaign_id=campaign_id,
                hour_of_day=hour,
                impressions=int(latest_impr * share),
                clicks=int(latest_clicks * share),
                cost_micros=int(latest_cost * share),
                conversions=round(latest_conv * share * conv_factor, 1),
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Day-of-week performance (weekends quieter) ----
    dow_names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    dow_weights = [1.0, 1.05, 1.05, 1.0, 0.95, 0.7, 0.65]
    dow_sum = sum(dow_weights)
    for dow_name, w in zip(dow_names, dow_weights, strict=True):
        share = w / dow_sum
        conv_factor = 0.85 if dow_name in ("SATURDAY", "SUNDAY") else 1.0
        rows["dow_perf"].append(
            DayOfWeekPerformanceSnapshotModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                snapshot_date=end_date,
                campaign_id=campaign_id,
                day_of_week=dow_name,
                impressions=int(latest_impr * share),
                clicks=int(latest_clicks * share),
                cost_micros=int(latest_cost * share),
                conversions=round(latest_conv * share * conv_factor, 1),
                created_at=now,
                updated_at=now,
            )
        )

    # ---- One PENDING recommendation matching the planted scenario, so the
    #      review UI / bulk-execute path has something to act on without
    #      first running the detection engine. ----
    rec = _scenario_recommendation(scenario, biz)
    if rec is not None:
        kind, severity, confidence, savings_pln, explanation = rec
        target = {"campaign_id": str(campaign_id), "campaign_name": f"{biz['city']} – Search"}
        target_hash = hashlib.sha256(f"{account_uuid}:{kind}:{campaign_id}".encode()).hexdigest()
        rows["recommendations"].append(
            RecommendationModel(
                id=uuid.uuid4(),
                account_id=account_uuid,
                kind=kind,
                severity=severity,
                confidence=confidence,
                status="PENDING",
                target=target,
                payload={"campaign_id": str(campaign_id)},
                evidence={"source": "demo_seed", "scenario": scenario},
                target_hash=target_hash,
                estimated_monthly_savings_micros=int(savings_pln * _PLN),
                explanation=explanation,
                created_at=now,
                updated_at=now,
            )
        )

    # ---- Notifications: a weekly digest + a weekly insight per account, so
    #      the in-app notification feed is populated. ----
    user_id_str = str(user_uuid)
    rows["notifications"].append(
        NotificationModel(
            id=uuid.uuid4(),
            user_id=user_id_str,
            notification_type="DIGEST",
            title="Tygodniowe podsumowanie kampanii",
            body=(
                f"W tym tygodniu Twoja kampania „{biz['city']} – Search\" wydała "
                f"{latest_cost / _PLN:.0f} PLN i przyniosła {latest_conv:.0f} konwersji."
            ),
            metadata_={"account_id": str(account_uuid), "source": "demo_seed"},
            read_at=None,
            created_at=now,
        )
    )
    rows["notifications"].append(
        NotificationModel(
            id=uuid.uuid4(),
            user_id=user_id_str,
            notification_type="INSIGHT",
            title="Cotygodniowa analiza",
            body=_scenario_insight(scenario, biz),
            metadata_={"account_id": str(account_uuid), "source": "demo_seed"},
            read_at=None,
            created_at=now,
        )
    )

    return rows


def _scenario_recommendation(scenario: str, biz: dict) -> tuple | None:
    """Map a planted scenario to (kind, severity, confidence, savings_pln, pl_explanation)."""
    mapping = {
        "cpa_spike": (
            "CPA_SPIKE", "CRITICAL", "HIGH", 1200.0,
            "Koszt pozyskania klienta wzrósł o ~95% w ostatnim tygodniu. "
            "Sprawdź stawki i jakość ruchu.",
        ),
        "cvr_drop": (
            "CONVERSION_RATE_DROP", "HIGH", "MEDIUM", 800.0,
            "Współczynnik konwersji spadł o ~50%. Zweryfikuj stronę docelową i śledzenie.",
        ),
        "low_qs": (
            "IMPROVE_QUALITY_SCORE", "HIGH", "HIGH", 600.0,
            "Wynik Jakości słowa kluczowego wynosi 3/10. Popraw trafność reklamy i strony.",
        ),
        "wasted_search_term": (
            "ADD_NEGATIVE_KEYWORD", "HIGH", "HIGH", 600.0,
            "Wykryto marnujące budżet zapytanie bez konwersji — dodaj słowo wykluczające.",
        ),
        "competitor_surge": (
            "NEW_COMPETITOR", "MEDIUM", "MEDIUM", 0.0,
            "Nowy konkurent (nowy-rywal.pl) pojawił się w aukcjach w ostatnich 7 dniach.",
        ),
        "budget_capped": (
            "INCREASE_BUDGET", "HIGH", "HIGH", 0.0,
            "Kampania traci ~40% udziału w wyświetleniach z powodu ograniczonego budżetu.",
        ),
        "spend_accel": (
            "SPEND_ACCELERATION", "CRITICAL", "HIGH", 1500.0,
            "Wydatki wzrosły o ~100% bez wzrostu konwersji. Sprawdź ustawienia stawek.",
        ),
        "no_tracking": (
            "ENABLE_CONVERSION_TRACKING", "CRITICAL", "HIGH", 0.0,
            "Brak aktywnego śledzenia konwersji — optymalizacja działa na ślepo.",
        ),
        "ad_fatigue": (
            "AD_FATIGUE", "MEDIUM", "MEDIUM", 300.0,
            "CTR reklamy spada przy stabilnych wyświetleniach — czas odświeżyć kreację.",
        ),
        "is_erosion": (
            "IMPRESSION_SHARE_EROSION", "HIGH", "MEDIUM", 400.0,
            "Udział w wyświetleniach spadł o ponad 15 pp. Sprawdź stawki i konkurencję.",
        ),
    }
    return mapping.get(scenario)


def _scenario_insight(scenario: str, biz: dict) -> str:
    """A short Polish weekly-insight body tailored to the scenario."""
    if scenario == "healthy":
        return (
            f"Kampania „{biz['city']} – Search\" działa powyżej średniej dla branży "
            f"{biz['vertical']}. Utrzymuj obecne ustawienia."
        )
    rec = _scenario_recommendation(scenario, biz)
    if rec is not None:
        return rec[4]
    return f"Przegląd kampanii „{biz['city']} – Search\" za miniony tydzień."


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


async def _reset_demo_data(session) -> None:
    """Delete all rows belonging to demo accounts (by the @demo.local marker)."""
    from sqlalchemy import delete, select

    user_ids = (
        (
            await session.execute(
                select(UserModel.id).where(UserModel.email.like(f"%@{_DEMO_EMAIL_DOMAIN}"))
            )
        )
        .scalars()
        .all()
    )
    if not user_ids:
        return
    account_ids = (
        (
            await session.execute(
                select(GoogleAdsAccountModel.id).where(GoogleAdsAccountModel.user_id.in_(user_ids))
            )
        )
        .scalars()
        .all()
    )
    snapshot_models = [
        CampaignSnapshotModel,
        AdGroupSnapshotModel,
        KeywordSnapshotModel,
        AdSnapshotModel,
        SearchTermSnapshotModel,
        ConversionActionSnapshotModel,
        AuctionInsightsSnapshotModel,
        BusinessEconomicsModel,
        NegativeKeywordSnapshotModel,
        CampaignExtensionSnapshotModel,
        DevicePerformanceSnapshotModel,
        GeoPerformanceSnapshotModel,
        HourPerformanceSnapshotModel,
        DayOfWeekPerformanceSnapshotModel,
        RecommendationModel,
    ]
    for model in snapshot_models:
        await session.execute(delete(model).where(model.account_id.in_(account_ids)))
    # Notifications key off user_id (string), not account_id.
    await session.execute(
        delete(NotificationModel).where(
            NotificationModel.user_id.in_([str(u) for u in user_ids])
        )
    )
    await session.execute(
        delete(GoogleAdsAccountModel).where(GoogleAdsAccountModel.id.in_(account_ids))
    )
    await session.execute(delete(UserModel).where(UserModel.id.in_(user_ids)))


async def _persist(all_rows: list[dict], *, reset: bool) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    engine = create_async_engine(get_settings().DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            if reset:
                await _reset_demo_data(session)
            for rows in all_rows:
                for _key, objs in rows.items():
                    session.add_all(objs)
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed scenario-rich demo accounts.")
    parser.add_argument("--accounts", type=int, default=len(DEMO_BUSINESSES))
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD; defaults to today")
    parser.add_argument("--reset", action="store_true", help="wipe prior demo data first")
    parser.add_argument("--dry-run", action="store_true", help="build rows in memory, no DB")
    parser.add_argument("--force", action="store_true", help="allow running when ENV=production")
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end_date) if args.end_date else datetime.now(tz=UTC).date()
    businesses = DEMO_BUSINESSES[: args.accounts]

    all_rows = [
        _build_account(biz, i, days=args.days, end_date=end_date)
        for i, biz in enumerate(businesses)
    ]

    counts: Counter = Counter()
    for rows in all_rows:
        for key, objs in rows.items():
            counts[key] += len(objs)

    print(f"Built {len(businesses)} demo businesses, {args.days} days ending {end_date}:")
    for key, n in sorted(counts.items()):
        print(f"  {key:20s} {n:>7,} rows")
    print(f"  {'TOTAL':20s} {sum(counts.values()):>7,} rows")
    for i, biz in enumerate(businesses):
        print(f"    #{i} {biz['vertical']:14s} {biz['scenario']:18s} {biz['name']}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    from adcopilot.config import get_settings

    settings = get_settings()
    if getattr(settings, "ENV", "") == "production" and not args.force:
        print("\nERROR: ENV=production. Refusing to seed demo data. Use --force to override.")
        return 2

    asyncio.run(_persist(all_rows, reset=args.reset))
    print(
        f"\nSeeded into {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'DB'}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
