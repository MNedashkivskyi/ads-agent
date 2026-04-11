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

**Goal:** Analyze the quality and relevance of ad copy using LLM. No competitor does this well.

**Data infrastructure needed:**
- `ad_group_ad.ad_strength` field in ad query
- LLM analysis port extended with `analyze_ad_relevance(keywords, ads)` method
- Templates for new recommendation kinds

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 17 | Ad-keyword mismatch | `AD_KEYWORD_MISMATCH` | HIGH | LLM relevance score < 0.6 between top keywords and ad headlines | ⬜ |
| 18 | Missing call-to-action | `MISSING_CTA` | MEDIUM | Ad copy contains no CTA verb (buy, sign up, get, call, book, try, start, learn) | ⬜ |
| 19 | Weak RSA asset strength | `WEAK_RSA_STRENGTH` | MEDIUM | RSA ad_strength = "POOR" or < 8 unique headlines | ⬜ |
| 20 | Ad fatigue | `AD_FATIGUE` | MEDIUM | Ad running >90 days with CTR declining >20% over last 30 days | ⬜ |
| 21 | Headline redundancy | `REDUNDANT_HEADLINES` | LOW | ≥3 RSA headlines share >60% token overlap with each other | ⬜ |
| 22 | Generic description | `GENERIC_DESCRIPTION` | LOW | Description lines contain no numbers, prices, or specific benefits (LLM-detected) | ⬜ |

---

## Module 3 — Campaign Structure & Organisation

**Goal:** Detect structural problems that prevent campaigns from performing, regardless of bids and budgets.

**Data infrastructure needed:**
- Cross-campaign keyword comparison (load all keywords across all accounts at once)
- Negative keyword lists (new GAQL query: `shared_set`, `shared_criterion`)
- Campaign-level negative keywords

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 23 | Overstuffed ad group | `OVERSTUFFED_AD_GROUP` | HIGH | Ad group has >15 enabled keywords | ⬜ |
| 24 | Keyword cannibalization | `KEYWORD_CANNIBALIZATION` | HIGH | Same keyword text in ≥2 active ad groups/campaigns | ⬜ |
| 25 | Negative keyword conflict | `NEGATIVE_KEYWORD_CONFLICT` | CRITICAL | A negative keyword is blocking a positive keyword in another group in the same campaign | ⬜ |
| 26 | Orphaned campaign | `ORPHANED_CAMPAIGN` | MEDIUM | Campaign has budget > 0 but all ad groups paused or empty | ⬜ |
| 27 | Match type redundancy | `MATCH_TYPE_REDUNDANCY` | LOW | Same keyword text added as both broad and exact in same ad group | ⬜ |

---

## Module 4 — Audience & Targeting Intelligence

**Goal:** Find money being wasted on the wrong devices, locations, hours, and demographics.

**Data infrastructure needed:**
- New GAQL queries: `segments.device`, `geographic_view`, `segments.hour_of_day`, `segments.day_of_week`, `age_range_view`, `gender_view`
- New snapshot tables or per-dimension metrics storage
- New DB models + migrations

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 28 | Device performance imbalance | `DEVICE_BID_ADJUSTMENT` | HIGH | Mobile CPA > 2× desktop CPA with ≥30 conv on desktop | ⬜ |
| 29 | Geographic waste | `GEO_EXCLUSION` | HIGH | Location with >€50 spend and 0 conversions, ≥20 clicks | ⬜ |
| 30 | Time-of-day waste | `AD_SCHEDULE_ADJUSTMENT` | MEDIUM | Hours with >€20 spend and 0 conversions across 30 days | ⬜ |
| 31 | Day-of-week CPA gap | `DAY_OF_WEEK_BID_ADJUSTMENT` | MEDIUM | Day-of-week avg CPA > 50% above account avg with ≥10 conversions | ⬜ |
| 32 | Missing audience signals | `ADD_AUDIENCE_SIGNALS` | LOW | Search campaign with 0 observation audiences and ≥1000 impressions | ⬜ |

---

## Module 5 — Budget & Bidding Strategy (expanded)

**Goal:** Find budget misallocation across campaigns and bidding strategy mismatches.

**Data infrastructure needed:**
- `metrics.search_impression_share`, `metrics.search_budget_lost_impression_share`, `metrics.search_rank_lost_impression_share` on campaign (added in Module 1)
- Multi-week campaign history for diminishing returns detection

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 33 | Budget misallocation | `REALLOCATE_BUDGET` | CRITICAL | Campaign A ROAS ≥ 3.0 and budget-capped while Campaign B ROAS < 1.0 and underspending | ⬜ |
| 34 | IS lost to budget | `INCREASE_BUDGET` (variant) | HIGH | search_budget_lost_impression_share > 30% | ⬜ |
| 35 | IS lost to rank | `IMPROVE_QUALITY_SCORE` | HIGH | search_rank_lost_impression_share > 30% | ⬜ |
| 36 | Target CPA too aggressive | `RELAX_TARGET_CPA` | MEDIUM | Target CPA < 50% of account avg CPA, campaign volume declining | ⬜ |
| 37 | Diminishing returns | `DIVERSIFY_CHANNELS` | MEDIUM | Budget increased ≥3 weeks in a row with <10% conversion increase per week | ⬜ |

---

## Module 6 — Conversion Tracking & Measurement (expanded)

**Goal:** Ensure the measurement foundation is solid. Bad tracking = every other decision is wrong.

**Data infrastructure needed:**
- New GAQL query: `conversion_action` resource
- `metrics.all_conversions`, `metrics.cross_device_conversions`, `metrics.view_through_conversions`

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 38 | Micro-conversion only | `UPGRADE_CONVERSION_ACTION` | HIGH | All tracked conversions are page views or button clicks (LLM-classified by name) | ⬜ |
| 39 | Duplicate conversion counting | `DEDUPLICATE_CONVERSIONS` | HIGH | Conversions far exceed expected based on spend and industry CPA (>5× account avg) | ⬜ |
| 40 | Conversion value missing | `SET_CONVERSION_VALUE` | MEDIUM | Conversions tracked but `conv_value` = 0 across all campaigns with ≥10 conversions | ⬜ |

---

## Module 7 — Ad Extensions & Assets

**Goal:** Ensure all available ad real estate is being used. Extensions improve CTR and ad rank at no extra cost.

**Data infrastructure needed:**
- New GAQL query: `campaign_extension_setting`, `ad_group_extension_setting`
- Extension performance metrics per asset

| # | Rule | Kind | Severity | Triggers when | Status |
|---|------|------|----------|--------------|--------|
| 41 | Missing sitelinks | `ADD_SITELINKS` | MEDIUM | Campaign ≥1000 impressions with no sitelink extension | ⬜ |
| 42 | Missing callouts | `ADD_CALLOUTS` | LOW | Campaign ≥1000 impressions with no callout extension | ⬜ |
| 43 | Missing structured snippets | `ADD_STRUCTURED_SNIPPETS` | LOW | Campaign ≥1000 impressions with no structured snippet | ⬜ |
| 44 | Low-performing sitelink | `REFRESH_SITELINK` | LOW | Sitelink CTR < 0.5% over 30 days with ≥500 impressions | ⬜ |

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
