# Breadth — Shopping / Performance Max

## Why
The product was ~95% Search-centric: 56 of 59 rules assumed Search, ingestion captured
no asset-group/listing-group data, and some Search rules could misfire on PMax/Shopping
campaigns. For ecommerce advertisers Shopping/PMax is the primary revenue lever. This
makes the product competent on Shopping/Performance Max, **within the existing Google
Ads API + OAuth scope** (no Merchant Center Content API), following the established
**advisory + safe-auto-fix** model.

## What landed
- **Channel-aware ingestion (SH0):** `query_asset_groups` + `query_listing_group_filters`
  GAQL (`infrastructure/google_ads/queries.py`); `AssetGroupSnapshot` / `ListingGroupSnapshot`
  domain; `asset_group_snapshots` / `listing_group_snapshots` tables (migration **0065**);
  repo upsert/load; ingestion in `SnapshotAccountUseCase` **only for accounts with a
  PMax/Shopping campaign** (quota-conscious, best-effort); threaded into `DetectionContext`.
- **Channel guard (SH1):** `application/detection/channel.py` (`is_search_campaign`,
  `is_pmax`, `is_shopping`, `is_pmax_or_shopping`). Budget/bidding rules **07, 10, 33, 36**
  now skip non-Search campaigns so they don't give Search-shaped advice on PMax/Shopping.
  (Keyword/ad-group/search-term rules already self-filter — they have no such data on PMax.)
- **PMax/Shopping advisory rules (SH1, Module 11):** `rule_60_pmax_asset_group_health.py` —
  `PMAX_ASSET_GROUP_WEAK` (ad strength POOR/AVERAGE), `PMAX_ASSET_GROUP_LIMITED`
  (primary status LIMITED/NOT_ELIGIBLE), `PMAX_FEED_SEGMENTATION` (spending campaign with
  only a catch-all listing group). All advisory (in `NON_EXECUTABLE_KINDS`).
- **Safe auto-fix (SH2):** `set_target_roas` mutation (port + adapter + fake);
  `ADJUST_PMAX_TARGET_ROAS` + `AdjustPmaxTargetRoasExecutor`. The spend guard
  (`domain/spend_guard.py`) bounds tROAS **loosening** (lowering the target raises spend);
  tightening is always safe.
- **Surfacing (SH3):** `GET /api/{user}/shopping/health` (`interfaces/api/shopping.py`) +
  frontend `routes/app/shopping.tsx` (ad-strength chips, serving status, catch-all warning)
  + nav + api-client/types + E2E spec.

## Testing & live validation
- **Unit-tested:** query row-parsing (mocked client), repo round-trip, context wiring, the
  three advisory rules (+ channel guard), the tROAS executor, the `set_target_roas` adapter
  proto shape (mocked), the spend-guard tROAS bounds, and the API response models.
- **Live-validated (post-deploy, dev account):** asset-group + listing-group queries return
  data; a PMax campaign surfaces asset-group / segmentation findings; the `set_target_roas`
  proto (no `validate_only`); and a Search budget rule no longer misfires on a PMax campaign.

## Explicitly deferred (separate efforts)
- **Demand Gen** — net-new channel (no code today).
- **Merchant Center Content API** — raw product-feed item health (disapprovals, GTIN/attr
  coverage) needs a new API + OAuth scope.
- **CRO actionable upgrade** — turning the landing-page audit into prioritized, actionable
  recommendations in the main rec stream.

## Guardrails
- Channel-correctness first: guarding Search rules from misfiring removes wrong advice.
- Advisory-by-default; the only executable addition is the bounded, spend-guarded tROAS change.
- Quota: asset/listing-group queries run only for accounts with PMax/Shopping campaigns.
- All user-facing copy Polish; no new PII; mutations reuse the spend-guard + audit path.
