"""Seed launch_structure v1 (demand-aware campaign-structure) prompt version.

The campaign-structure stage now instructs the model to prefer high-intent,
real-demand keywords (real Keyword Planner volumes are applied immediately
after this stage by the keyword-enrichment service). Per the project rule, a
prompt is the version of record in the database: this records the structure
system prompt as ``launch_structure`` v1. Kept identical to
``adcopilot.infrastructure.llm.campaign_generator._STRUCTURE_SYSTEM``.

Revision ID: 0067
Revises: 0066
Create Date: 2026-06-04
"""

from __future__ import annotations

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

_PROMPT_KEY = "launch_structure"
_VERSION = 1

_CONTENT = """\
You are an expert Google Ads campaign architect.
Design a complete campaign skeleton from the business brief and vertical.
IMPORTANT: Follow the budget-tier structure constraints provided in the user prompt exactly.
The bidding strategy has been pre-selected — use it as-is, do not change it.
Prefer keywords with genuine search demand and commercial intent: favour the
specific terms real customers type (service + city, "near me", buying/booking
intent) over ultra-generic single words with little intent. Real search-volume
data is applied after this step, so concrete, high-intent keywords survive.
Respond ONLY with a valid JSON object matching this schema — no markdown, no prose:
{
  "campaign_name": "<string ≤ 120 chars>",
  "bidding_strategy": "<use the pre-selected strategy from the user prompt>",
  "ad_groups": [
    {
      "name": "<string>",
      "theme": "<short theme description>",
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
