# AdCopilot — Campaign Analysis Roadmap

This document describes the full planned detection system: all modules, rules, data requirements, and implementation status.

The current 10 hygiene rules are the baseline. This roadmap expands the system into a professional-grade analysis platform that answers not just "what is broken?" but "why is this not working and what is the best fix?"

---

## Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented |
| 🚧 | In progress |
| ⬜ | Planned |
| ❌ | Known bug / broken |

---

## Module 0 — Hygiene (existing baseline)

Basic checks every PPC specialist runs manually. These remain but are not sufficient on their own.

| # | Rule | Kind | Severity | Status |
|---|------|------|----------|--------|
| 01 | Wasted search term (≥5 clicks, 0 conv, cost ≥30% avg CPA, waste-signal words) | `ADD_NEGATIVE_KEYWORD` | HIGH | ✅ |
| 02 | Zero-conversion keyword (≥30 clicks, 0 conv, cost ≥2× avg CPA) | `PAUSE_KEYWORD` | HIGH | ✅ |
| 03 | Low quality score (QS ≤ 4, cost ≥ €10) | `PAUSE_KEYWORD` | MEDIUM | ✅ |
| 04 | Disapproved ad | `FIX_DISAPPROVED_AD` | CRITICAL | ✅ |
| 05 | Broad match bleeding (≥10 search terms, ≥30% Jaccard-unrelated) | `CHANGE_MATCH_TYPE` | MEDIUM | ✅ fixed — groups by `ad_group_id` instead of broken `matched_keyword_id` |
| 06 | No conversion tracking (cost ≥ €100, 0 conversions account-wide) | `ENABLE_CONVERSION_TRACKING` | CRITICAL | ✅ |
| 07 | Budget capped (daily avg ≥ 95% of budget, ROAS > 1.0) | `INCREASE_BUDGET` | HIGH | ✅ |
| 08 | Single ad in group (exactly 1 active ad, ≥100 impressions) | `ADD_AD_VARIATION` | LOW | ✅ |
| 09 | Dead keyword (0 impressions, status = ENABLED) | `PAUSE_KEYWORD` | LOW | ✅ |
| 10 | Wrong bidding strategy (MAXIMIZE_CLICKS with ≥30 conversions) | `ADJUST_BIDDING_STRATEGY` | MEDIUM | ✅ |

---

## Module 1 — Performance Degradation & Trends

**Goal:** Detect when something was working and has stopped, or is trending in the wrong direction. This requires multi-day snapshot comparison.

**Data infrastructure needed:**
- Snapshot repository must support range queries (`get_keywords_by_date`, `get_campaigns_by_date`)
- `DetectionContext` extended with `prev_7d_keywords` and `prev_7d_campaigns` (7-day-ago snapshot)
- `CampaignSnapshot` extended with `search_impression_share`, `search_budget_lost_impression_share`, `search_rank_lost_impression_share`
- New GAQL fields on campaign query for impression share metrics
- New DB columns + Alembic migration

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 11 | CTR decline | `CTR_DECLINE` | HIGH | Ad group CTR dropped >30% WoW, impressions stable (change <20%) | ✅ |
| 12 | CPA spike | `CPA_SPIKE` | HIGH | Campaign cost-per-conversion increased >50% WoW, ≥5 conversions in both periods | ✅ |
| 13 | Conversion rate drop | `CONVERSION_RATE_DROP` | HIGH | Campaign click-to-conversion rate dropped >25% WoW, ≥50 clicks in both periods | ✅ |
| 14 | Impression share erosion | `IMPRESSION_SHARE_EROSION` | MEDIUM | Search impression share dropped >15 percentage points WoW | ✅ |
| 15 | Spend acceleration without results | `SPEND_ACCELERATION` | CRITICAL | Campaign cost increased >30% WoW but conversions flat or declining | ✅ |
| 16 | Quality score deterioration | `QUALITY_SCORE_DETERIORATION` | MEDIUM | Keyword QS dropped ≥2 points vs 7-day-ago snapshot | ✅ |

---

## Module 2 — Ad Copy & Creative Intelligence

**Goal:** Analyze the quality and relevance of ad copy using heuristic token analysis. LLM is used only for the explanation step (existing `ExplainRecommendationUseCase`), keeping nightly batch jobs fast and cost-efficient.

**Data infrastructure delivered:**
- `ad_group_ad.ad_strength` field added to ad query + DB model + migration 0013
- `prev_ads` historical snapshot added to `DetectionContext`
- EN + PL explanation templates added for all 6 kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 17 | Ad-keyword mismatch | `AD_KEYWORD_MISMATCH` | HIGH | Keyword token coverage in ad headlines < 35% | ✅ |
| 18 | Missing call-to-action | `MISSING_CTA` | MEDIUM | Ad copy contains no CTA verb (EN + PL, regex) | ✅ |
| 19 | Weak RSA asset strength | `WEAK_RSA_STRENGTH` | MEDIUM | RSA ad_strength = "POOR"/"AVERAGE" or < 8 unique headlines | ✅ |
| 20 | Ad fatigue | `AD_FATIGUE` | MEDIUM | CTR dropped >25% WoW with stable impressions (±20%) | ✅ |
| 21 | Headline redundancy | `REDUNDANT_HEADLINES` | LOW | ≥3 RSA headlines share >60% Jaccard token overlap | ✅ |
| 22 | Generic description | `GENERIC_DESCRIPTION` | LOW | All descriptions lack digits, currency symbols, percentages, or anchor words | ✅ |

---

## Module 3 — Campaign Structure & Organisation

**Goal:** Detect structural problems that prevent campaigns from performing, regardless of bids and budgets.

**Data infrastructure delivered:**
- `NegativeKeywordSnapshot` domain entity + `negative_keyword_snapshots` DB table (migration 0014)
- GAQL queries for both campaign-level and ad-group-level negative keywords
- `negative_keywords` field added to `SnapshotData`, `DetectionContext`, and `SnapshotResult`
- `query_negative_keywords` added to `GoogleAdsClientPort` and infrastructure implementation
- EN + PL explanation templates for all 5 kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 23 | Overstuffed ad group | `OVERSTUFFED_AD_GROUP` | HIGH | Ad group has > 15 enabled keywords | ✅ |
| 24 | Keyword cannibalization | `KEYWORD_CANNIBALIZATION` | HIGH | Same keyword text in ≥ 2 active ad groups/campaigns | ✅ |
| 25 | Negative keyword conflict | `NEGATIVE_KEYWORD_CONFLICT` | CRITICAL | A negative keyword blocks a positive keyword in the same campaign or ad group | ✅ |
| 26 | Orphaned campaign | `ORPHANED_CAMPAIGN` | MEDIUM | Campaign enabled with budget > 0 but all ad groups paused or removed | ✅ |
| 27 | Match type redundancy | `MATCH_TYPE_REDUNDANCY` | LOW | Same keyword text added as both BROAD and EXACT/PHRASE in the same ad group | ✅ |

---

## Module 4 — Audience & Targeting Intelligence

**Goal:** Find money being wasted on the wrong devices, locations, hours, and demographics.

**Data infrastructure delivered:**
- 5 new GAQL queries: `segments.device`, `geographic_view`, `segments.hour_of_day`, `segments.day_of_week`, `ad_group_audience_view`
- 5 new snapshot domain entities + DB models: `DevicePerformanceSnapshot`, `GeoPerformanceSnapshot`, `HourPerformanceSnapshot`, `DayOfWeekPerformanceSnapshot`, `AudiencePerformanceSnapshot`
- Migration 0015 creating all 5 targeting performance tables
- 30-day windowed data loading in `_load_targeting_performance` for geo/hour/day-of-week; 7-day window for device
- EN + PL explanation templates for all 5 kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 28 | Device performance imbalance | `DEVICE_BID_ADJUSTMENT` | HIGH | Mobile CPA > 2× desktop CPA with ≥30 conv on desktop | ✅ |
| 29 | Geographic waste | `GEO_EXCLUSION` | HIGH | Location with >€50 spend and 0 conversions, ≥20 clicks | ✅ |
| 30 | Time-of-day waste | `AD_SCHEDULE_ADJUSTMENT` | MEDIUM | Hours with >€20 spend and 0 conversions across 30 days | ✅ |
| 31 | Day-of-week CPA gap | `DAY_OF_WEEK_BID_ADJUSTMENT` | MEDIUM | Day-of-week avg CPA > 50% above account avg with ≥10 conversions | ✅ |
| 32 | Missing audience signals | `ADD_AUDIENCE_SIGNALS` | LOW | Search campaign with 0 observation audiences and ≥1000 impressions | ✅ |

---

## Module 5 — Budget & Bidding Strategy (expanded)

**Goal:** Find budget misallocation across campaigns and bidding strategy mismatches.

**Data infrastructure delivered:**
- `target_cpa_micros: int | None` added to `CampaignSnapshot`, `CampaignSnapshotModel`, and GAQL query
- Migration 0016 adding nullable `target_cpa_micros` column to `campaign_snapshots`
- All impression share metrics (`search_budget_lost_impression_share`, `search_rank_lost_impression_share`) already available from Module 1
- Week-over-week comparison via `prev_campaigns` already loaded from Module 1
- EN + PL explanation templates for all 4 new kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 33 | Budget misallocation | `REALLOCATE_BUDGET` | CRITICAL | Campaign A ROAS ≥ 3.0 and budget-capped (≥95% util) while Campaign B ROAS < 1.0 and underspending (<50% util) | ✅ |
| 34 | IS lost to budget | `INCREASE_BUDGET` (variant) | HIGH | search_budget_lost_impression_share > 30% | ✅ |
| 35 | IS lost to rank | `IMPROVE_QUALITY_SCORE` | HIGH | search_rank_lost_impression_share > 30% | ✅ |
| 36 | Target CPA too aggressive | `RELAX_TARGET_CPA` | MEDIUM | TARGET_CPA campaign with target < 50% of account avg CPA and < 5 conversions | ✅ |
| 37 | Diminishing returns | `DIVERSIFY_CHANNELS` | MEDIUM | Spend grew ≥20% week-over-week but conversions grew <10% | ✅ |

---

## Module 6 — Conversion Tracking & Measurement (expanded)

**Goal:** Ensure the measurement foundation is solid. Bad tracking = every other decision is wrong.

**Data infrastructure delivered:**
- `ConversionActionSnapshot` domain entity + `conversion_action_snapshots` DB table (migration 0018)
- `query_conversion_actions` GAQL query fetching action name, category, counting type, status, include_in_conversions_metric
- `all_conversions: float` added to `CampaignSnapshot` + `campaign_snapshots` column (migration 0017)
- `SnapshotAccountUseCase` now fetches 12 entity types in parallel
- `conversion_actions` field added to `DetectionContext`
- EN + PL explanation templates for all 3 kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 38 | Micro-conversion only | `UPGRADE_CONVERSION_ACTION` | HIGH | All ENABLED included conversions are PAGE_VIEW/DEFAULT or have micro-signal names (no LLM needed) | ✅ |
| 39 | Duplicate conversion counting | `DEDUPLICATE_CONVERSIONS` | HIGH | `all_conversions` > 5× `conversions` across enabled campaigns | ✅ |
| 40 | Conversion value missing | `SET_CONVERSION_VALUE` | MEDIUM | ≥10 conversions tracked but `conv_value` = 0 across all enabled campaigns | ✅ |

---

## Module 7 — Ad Extensions & Assets

**Goal:** Ensure all available ad real estate is being used. Extensions improve CTR and ad rank at no extra cost.

**Data infrastructure delivered:**
- `CampaignExtensionSnapshot` domain entity + `campaign_extension_snapshots` DB table (migration 0019)
- `SitelinkPerformanceSnapshot` domain entity + `sitelink_performance_snapshots` DB table (migration 0019)
- GAQL queries: `query_campaign_extensions` (from `campaign_extension_setting`) + `query_sitelink_performance` (from `campaign_asset`)
- `campaign_extensions` and `sitelink_performance` fields added to `DetectionContext`
- `SnapshotAccountUseCase` now fetches 14 entity types in parallel
- EN + PL explanation templates added for all 4 kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 41 | Missing sitelinks | `ADD_SITELINKS` | MEDIUM | Campaign ≥1000 impressions with no sitelink extension | ✅ |
| 42 | Missing callouts | `ADD_CALLOUTS` | LOW | Campaign ≥1000 impressions with no callout extension | ✅ |
| 43 | Missing structured snippets | `ADD_STRUCTURED_SNIPPETS` | LOW | Campaign ≥1000 impressions with no structured snippet | ✅ |
| 44 | Low-performing sitelink | `REFRESH_SITELINK` | LOW | Sitelink CTR < 0.5% over 30 days with ≥500 impressions | ✅ |

---

## Implementation order

1. **Module 0 bug fix** — Rule 05 (`matched_keyword_id` always `None`) → fix GAQL query
2. **Module 1** — Trend detection (requires infrastructure: multi-day context, impression share fields)
3. **Module 2** — Ad copy analysis (requires LLM port extension)
4. **Module 3** — Structure analysis (requires cross-campaign data loading)
5. **Module 5** — Budget/bidding expansion (impression share infra reused from Module 1)
6. **Module 4** — Audience targeting (requires 5 new GAQL queries + new DB tables)
7. **Module 6** — Conversion tracking (requires conversion_action query)
8. **Module 7** — Extensions (requires extension queries)
