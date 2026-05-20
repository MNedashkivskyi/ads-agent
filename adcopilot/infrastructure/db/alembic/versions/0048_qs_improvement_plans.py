"""0048 — QS improvement plans table + prompt version seed.

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qs_improvement_plans",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("keyword_criterion_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("target_ad_group_resource_name", sa.VARCHAR(256), nullable=True),
        sa.Column("current_avg_qs", sa.Float(), nullable=True),
        sa.Column("target_qs", sa.Float(), nullable=False, server_default="7.0"),
        sa.Column("bottleneck_component", sa.VARCHAR(64), nullable=False),
        sa.Column("prescribed_actions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.VARCHAR(32), nullable=False, server_default="PROPOSED"),
        sa.Column("baseline_metrics", sa.JSON(), nullable=True),
        sa.Column("current_metrics", sa.JSON(), nullable=True),
        sa.Column("evaluation_summary_pl", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measurement_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_qs_improvement_plans_account_id",
        "qs_improvement_plans",
        ["account_id"],
    )
    op.create_index(
        "ix_qs_improvement_plans_status",
        "qs_improvement_plans",
        ["status"],
    )

    # Seed prompt version for QS improvement plan
    op.execute(
        """
        INSERT INTO prompt_versions (prompt_key, version, content, created_at)
        VALUES (
            'qs_improvement_plan_v1',
            1,
            'Jesteś ekspertem Google Ads. Przeanalizuj plan poprawy Quality Score i wygeneruj diagnozę po polsku.',
            NOW()
        )
        ON CONFLICT ON CONSTRAINT uq_prompt_versions_key_version DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_qs_improvement_plans_status", "qs_improvement_plans")
    op.drop_index("ix_qs_improvement_plans_account_id", "qs_improvement_plans")
    op.drop_table("qs_improvement_plans")
