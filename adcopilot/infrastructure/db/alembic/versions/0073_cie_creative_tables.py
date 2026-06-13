"""CIE creative track — hook sets, candidates, shipped assets + prompt seeds.

Revision ID: 0073
Revises: 0072
Create Date: 2026-06-13
"""

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402

from adcopilot.infrastructure.prompts.hook_generation import (  # noqa: E402
    HOOK_GENERATION_PROMPT_KEY,
    SEED_CONTENT as HOOK_GEN_SEED,
)
from adcopilot.infrastructure.prompts.hook_judge import (  # noqa: E402
    HOOK_JUDGE_PROMPT_KEY,
    SEED_CONTENT as HOOK_JUDGE_SEED,
)


def upgrade() -> None:
    op.create_table(
        "cie_hook_sets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("service", sa.Text(), server_default="", nullable=False),
        sa.Column("problems", JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(20), server_default="generating", nullable=False),
        sa.Column("rsa_payload", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cie_hook_sets_campaign_id", "cie_hook_sets", ["campaign_id"])
    op.create_index("ix_cie_hook_sets_account_id", "cie_hook_sets", ["account_id"])
    op.create_index("ix_cie_hook_sets_user_id", "cie_hook_sets", ["user_id"])
    op.create_index("ix_cie_hook_sets_status", "cie_hook_sets", ["status"])

    op.create_table(
        "cie_hook_candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("set_id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("angle", sa.String(32), nullable=False),
        sa.Column("surface", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("policy_risk", sa.String(10), server_default="LOW", nullable=False),
        sa.Column("policy_reason", sa.Text(), server_default="", nullable=False),
        sa.Column("judge_score", sa.Float(), nullable=True),
        sa.Column("heuristic_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("status", sa.String(16), server_default="generated", nullable=False),
        sa.Column("pinned_slot", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["set_id"], ["cie_hook_sets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_cie_hook_candidates_set_id", "cie_hook_candidates", ["set_id"])
    op.create_index("ix_cie_hook_candidates_campaign_id", "cie_hook_candidates", ["campaign_id"])
    op.create_index("ix_cie_hook_candidate_set_status", "cie_hook_candidates", ["set_id", "status"])

    op.create_table(
        "cie_shipped_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.String(32), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column("asset_id", sa.String(40), nullable=True),
        sa.Column("asset_text", sa.Text(), nullable=False),
        sa.Column("angle", sa.String(32), nullable=False),
        sa.Column("surface", sa.String(20), nullable=False),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "customer_id", "asset_text", "surface", name="uq_cie_shipped_asset"),
    )
    op.create_index("ix_cie_shipped_assets_account_id", "cie_shipped_assets", ["account_id"])
    op.create_index("ix_cie_shipped_assets_customer_id", "cie_shipped_assets", ["customer_id"])
    op.create_index("ix_cie_shipped_asset_text", "cie_shipped_assets", ["asset_text"])
    op.create_index("ix_cie_shipped_asset_id", "cie_shipped_assets", ["asset_id"])

    for key, content in (
        (HOOK_GENERATION_PROMPT_KEY, HOOK_GEN_SEED),
        (HOOK_JUDGE_PROMPT_KEY, HOOK_JUDGE_SEED),
    ):
        op.execute(
            sa.text(
                "INSERT INTO prompt_versions (prompt_key, version, content) "
                "VALUES (:key, 1, :content) ON CONFLICT (prompt_key, version) DO NOTHING"
            ).bindparams(key=key, content=content)
        )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM prompt_versions WHERE prompt_key IN (:k1, :k2)").bindparams(
            k1=HOOK_GENERATION_PROMPT_KEY, k2=HOOK_JUDGE_PROMPT_KEY
        )
    )
    op.drop_index("ix_cie_shipped_asset_id", table_name="cie_shipped_assets")
    op.drop_index("ix_cie_shipped_asset_text", table_name="cie_shipped_assets")
    op.drop_index("ix_cie_shipped_assets_customer_id", table_name="cie_shipped_assets")
    op.drop_index("ix_cie_shipped_assets_account_id", table_name="cie_shipped_assets")
    op.drop_table("cie_shipped_assets")
    op.drop_index("ix_cie_hook_candidate_set_status", table_name="cie_hook_candidates")
    op.drop_index("ix_cie_hook_candidates_campaign_id", table_name="cie_hook_candidates")
    op.drop_index("ix_cie_hook_candidates_set_id", table_name="cie_hook_candidates")
    op.drop_table("cie_hook_candidates")
    op.drop_index("ix_cie_hook_sets_status", table_name="cie_hook_sets")
    op.drop_index("ix_cie_hook_sets_user_id", table_name="cie_hook_sets")
    op.drop_index("ix_cie_hook_sets_account_id", table_name="cie_hook_sets")
    op.drop_index("ix_cie_hook_sets_campaign_id", table_name="cie_hook_sets")
    op.drop_table("cie_hook_sets")
