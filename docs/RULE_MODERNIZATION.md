# Smart Bidding Rule Modernization — disposition map

Under conversion-based Smart Bidding (Maximize Conversions/Value, tCPA, tROAS),
Google ignores manual bid adjustments and broad match + good signals is the
recommended path. These rules previously fired regardless of bidding strategy,
producing confident-but-wrong advice. Each rule now resolves the affected
campaign's bidding mode via `application/detection/bidding.py` and adapts.

Conservative default: unknown/empty strategy → MANUAL (never wrongly suppress).

| Rule | Disposition on Smart Bidding | Rationale |
|---|---|---|
| `rule_28_device_bid_adjustment` | **Suppressed** | Device bid adjustments are ignored under Smart Bidding (it optimizes per-device). |
| `rule_30_ad_schedule_adjustment` | **Suppressed** | Hourly bid adjustments are ignored; Smart Bidding sets intraday bids. |
| `rule_31_day_of_week_bid_adjustment` | **Suppressed** | Day-of-week bid adjustments are ignored. |
| `rule_27_match_type_redundancy` | **Suppressed** | Broad alongside exact/phrase is a valid (recommended) structure. |
| `rule_05_broad_match_bleeding` | **Suppressed** | Broad + Smart Bidding is recommended; wasteful terms are still mined as negatives by `rule_01_wasted_search_term`. |
| `rule_29_geo_exclusion` | **Kept** | Location *exclusions* remain valid under Smart Bidding (not a bid modifier). |

Other manual-era surface (e.g. `rule_10_wrong_bidding_strategy`) already keys off
`bidding_strategy` and is unchanged.

All recommendations also carry a **confidence** level (LOW/MEDIUM/HIGH) graded by
data sufficiency (`confidence_from_volume`), surfaced on the recommendations page.

# Rule cleanup (executability)

## Now executable (P1)
The ad-copy cluster reuses the shared `AdCopyRefreshExecutor` (generates a fresh
RSA in the ad group; non-destructive): `ADD_AD_VARIATION` (08), `AD_KEYWORD_MISMATCH`
(17), `MISSING_CTA` (18), `REDUNDANT_HEADLINES` (21), `GENERIC_DESCRIPTION` (22) —
alongside the pre-existing `AD_FATIGUE` / `WEAK_RSA_STRENGTH`.

## Correctness/hygiene (P2)
- `rule_54_device_campaign_split` now emits the advisory kind `DEVICE_CAMPAIGN_SPLIT`
  (in `NON_EXECUTABLE_KINDS`). Previously it emitted `DEVICE_BID_ADJUSTMENT`, so
  approving applied a bid modifier — the wrong action. The legitimate device-bid
  rule (28) keeps `DEVICE_BID_ADJUSTMENT` executable.
- Removed the orphaned `executors/audience_bid_adjustment.py` (free function, not
  protocol-compatible, unreferenced). `AUDIENCE_BID_ADJUSTMENT` stays advisory
  until a protocol executor is built.

## Duplicate-kind overlaps (dedup via target_hash)
Several rules intentionally share a `kind`; dedup is by `(kind, target_hash)` in
`list_active_dedup_keys`, so the same issue on the same target yields one card:
- `ORPHANED_CAMPAIGN`: 26 & 52 · `OVERSTUFFED_AD_GROUP`: 23 & 53 ·
  `IMPROVE_QUALITY_SCORE`: 35 & 51 · `INCREASE_BUDGET`: 07 & 34 & 58 ·
  `AUDIENCE_BID_ADJUSTMENT`: 55 & 56.

## Still advisory by design
Performance alerts (11–16), 04 disapproved, 06 conversion tracking, structural
(23/24/26/52/53), QS (35/51), 37 diversify, 45 landing page, 48 benchmark,
49/50 PMax, competitor rules, audience expansion / 57 lookalike.

## Remaining executable gaps (P3, planned)
`SET_CONVERSION_VALUE` (40), `UPGRADE_CONVERSION_ACTION` (38),
`DEDUPLICATE_CONVERSIONS` (39), `REFRESH_SITELINK` (44), `DAY_OF_WEEK_BID_ADJUSTMENT` (31).
