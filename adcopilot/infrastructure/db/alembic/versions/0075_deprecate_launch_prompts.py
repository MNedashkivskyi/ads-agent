"""Deprecate the launch (campaign-creation) prompts — T2.4.

Greenfield campaign creation was retired in the optimization pivot. The
``launch_structure`` and ``launch_ad_copy`` prompts are no longer used by any
live code, but the prompt-versioning rule forbids deleting prompt rows. This
migration adds a ``deprecated`` flag to ``prompt_versions`` and sets it for those
two keys, preserving their full version history. The optimization prompts
(cie_*, ad_copy_refresh_v1, landing_page_score_v1, weekly_insight_v1,
client_qa_v1, audience_strategy_v1, seasonality_v1, custom_intent_v1,
performance_report_v1, conversion_tracking_audit_v1) are left untouched.

Revision ID: 0075
Revises: 0074
Create Date: 2026-06-16
"""

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402

_DEPRECATED_KEYS = ("launch_structure", "launch_ad_copy")


def upgrade() -> None:
    op.add_column(
        "prompt_versions",
        sa.Column(
            "deprecated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE prompt_versions SET deprecated = true "
            "WHERE prompt_key IN ('launch_structure', 'launch_ad_copy')"
        )
    )


def downgrade() -> None:
    op.drop_column("prompt_versions", "deprecated")
