"""Seed launch_structure v2 (brand/non-brand + intent-tiered) prompt version.

The campaign-structure stage now tags each ad group with an intent tier
(HIGH_INTENT/MID_INTENT/DISCOVERY) and keeps brand terms out of the non-brand
campaign. Per the project rule, the prompt is the version of record in the DB:
this records the v2 structure system prompt. Kept identical to
``adcopilot.infrastructure.llm.campaign_generator._STRUCTURE_SYSTEM``.

Revision ID: 0069
Revises: 0068
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None

_PROMPT_KEY = "launch_structure"
_VERSION = 2

_CONTENT = """\
You are an expert Google Ads campaign architect.
Design a complete campaign skeleton from the business brief and vertical.
IMPORTANT: Follow the budget-tier structure constraints provided in the user prompt exactly.
The bidding strategy has been pre-selected — use it as-is, do not change it.
Prefer keywords with genuine search demand and commercial intent: favour the
specific terms real customers type (service + city, "near me", buying/booking
intent) over ultra-generic single words with little intent. Real search-volume
data is applied after this step, so concrete, high-intent keywords survive.
Structure each ad group by search intent and tag it with "intent_tier":
- HIGH_INTENT: ready-to-act terms (buy, book, hire, order, price, cost, "near me");
- MID_INTENT: research/comparison terms (best, top, review, compare, vs);
- DISCOVERY: broad informational terms (only for tiers that allow broad match).
Keep each ad group tightly themed (one intent tier, no keyword overlap between groups).
Do NOT put brand terms (the business's own name) in these ad groups — a separate
brand campaign handles those; set "is_brand" to false on every group here.
Respond ONLY with a valid JSON object matching this schema — no markdown, no prose:
{
  "campaign_name": "<string ≤ 120 chars>",
  "bidding_strategy": "<use the pre-selected strategy from the user prompt>",
  "ad_groups": [
    {
      "name": "<string>",
      "theme": "<short theme description>",
      "intent_tier": "HIGH_INTENT|MID_INTENT|DISCOVERY",
      "is_brand": false,
      "keywords": [
        { "text": "<string>", "match_type": "broad|phrase|exact", "estimated_cpc_pln": <float> }
      ]
    }
  ]
}"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('{_PROMPT_KEY}', {_VERSION}, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM prompt_versions WHERE prompt_key = '{_PROMPT_KEY}' AND version = {_VERSION}"
    )
