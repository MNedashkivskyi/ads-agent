# Phase 1 / T1.4 — launch-domain import audit

Greenfield campaign creation is disabled behind the reversible kill-switch
(`CAMPAIGN_CREATION_ENABLED`, default off — see T1.1/T1.2). Per the plan's
guiding decision, **physical deletion of the creation code is deferred to T6.2**
after a stabilization window. This note records the audit that T6.2 must act on
so that deleting `adcopilot/domain/launch/` does not strand optimization.

## Shared modules that MUST be moved out of `domain/launch/` before T6.2 deletes the package

These three are imported by **live optimization** code and are not
creation-bound. T6.2 should relocate them (e.g. to `adcopilot/domain/`) and
update importers:

| Module | Live (kept) importers |
|---|---|
| `conversion_tracking_status.py` | `infrastructure/adapters/google_ads_conversion_adapter.py`, `application/ports/conversion_tracking_checker.py` |
| `pagespeed_result.py` | `infrastructure/adapters/google_pagespeed_adapter.py`, `application/ports/pagespeed_analyzer.py` |
| `website_intelligence.py` | `infrastructure/adapters/http_website_crawler.py`, `application/services/website_intelligence_extractor.py`, `application/ports/website_crawler.py` |

## `domain/launch/entities.py` — partially shared

`entities.py` is imported by optimization code that stays:

- `application/detection/validation.py` → `CampaignBrief`, `CampaignProposal`
- `infrastructure/cie/proposal_enhancer.py`, `infrastructure/cie/campaign_context.py` (CIE — Phase 2 / T2.1 decouples these from the launch brief)
- `infrastructure/google_ads/pmax_writer.py`, `application/use_cases/create_pmax_campaign.py` → `PMaxCampaignProposal`, `AssetGroupProposal`

Before T6.2 can drop `entities.py`, the still-needed entities (the PMax
proposal types and anything detection/CIE relies on after T2.1) must be moved
to a non-launch module. The brief/proposal state-machine entities
(`CampaignBrief`, `LaunchStatus`, `RemarketingCampaignProposal`) are
creation-only and can be deleted with the launch flow.

## Creation-only modules (safe for T6.2 to delete with the launch flow)

`budget_tier.py`, `bidding_resolver.py`, `schedule_rules.py`, `structure_rules.py`,
`audience_signals.py`, `templates.py`, `vertical_template.py`, `validator.py`,
`model_tier.py`, plus `infrastructure/vertical_templates/yaml_adapter.py` and
`config/verticals/*.yaml`. Note `structure_rules.py` and `budget_tier.py` are
currently also referenced by CIE (`proposal_enhancer.py`) and the template
assembler — confirm those call sites are gone after Phase 2 before deleting.

## Tables

Dropping the brief/proposal tables is deferred to the data-retention review in
T6.1 (do not drop in Phase 1).

## Status after Phase 1

No launch-domain modules were deleted or moved in Phase 1. The app and worker
import cleanly; creation is inert because the routes 404 (T1.1) and the tasks
no-op (T1.2). This audit is the contract T6.2 executes.
