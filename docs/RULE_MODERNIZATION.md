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
