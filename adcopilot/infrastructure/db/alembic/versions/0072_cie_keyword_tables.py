"""CIE keyword track — runs + candidates tables and the generation prompt seed.

Revision ID: 0072
Revises: 0071
Create Date: 2026-06-13
"""

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402

from adcopilot.infrastructure.prompts.keyword_generation import (  # noqa: E402
    KEYWORD_GENERATION_PROMPT_KEY,
    SEED_CONTENT,
)


def upgrade() -> None:
    op.create_table(
        "cie_keyword_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("vertical", sa.String(64), server_default="generic", nullable=False),
        sa.Column("language", sa.String(10), server_default="pl", nullable=False),
        sa.Column("service", sa.Text(), server_default="", nullable=False),
        sa.Column("problems", JSONB(), server_default="[]", nullable=False),
        sa.Column("seeds", JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(20), server_default="generating", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cie_keyword_runs_campaign_id", "cie_keyword_runs", ["campaign_id"])
    op.create_index("ix_cie_keyword_runs_account_id", "cie_keyword_runs", ["account_id"])
    op.create_index("ix_cie_keyword_runs_user_id", "cie_keyword_runs", ["user_id"])
    op.create_index("ix_cie_keyword_runs_status", "cie_keyword_runs", ["status"])

    op.create_table(
        "cie_keyword_candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("campaign_id", sa.UUID(), nullable=False),
        sa.Column("phrase", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), server_default="llm", nullable=False),
        sa.Column("reasoning", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(16), server_default="generated", nullable=False),
        sa.Column("monthly_searches", sa.Integer(), nullable=True),
        sa.Column("competition", sa.String(16), nullable=True),
        sa.Column("cpc_low_micros", sa.BigInteger(), nullable=True),
        sa.Column("cpc_high_micros", sa.BigInteger(), nullable=True),
        sa.Column("is_bucketed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["cie_keyword_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "phrase", name="uq_cie_keyword_candidate_phrase"),
    )
    op.create_index("ix_cie_keyword_candidates_run_id", "cie_keyword_candidates", ["run_id"])
    op.create_index(
        "ix_cie_keyword_candidates_campaign_id", "cie_keyword_candidates", ["campaign_id"]
    )
    op.create_index(
        "ix_cie_keyword_candidate_run_status", "cie_keyword_candidates", ["run_id", "status"]
    )

    op.execute(
        sa.text(
            "INSERT INTO prompt_versions (prompt_key, version, content) "
            "VALUES (:key, 1, :content) "
            "ON CONFLICT (prompt_key, version) DO NOTHING"
        ).bindparams(key=KEYWORD_GENERATION_PROMPT_KEY, content=SEED_CONTENT)
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM prompt_versions WHERE prompt_key = :key").bindparams(
            key=KEYWORD_GENERATION_PROMPT_KEY
        )
    )
    op.drop_index("ix_cie_keyword_candidate_run_status", table_name="cie_keyword_candidates")
    op.drop_index("ix_cie_keyword_candidates_campaign_id", table_name="cie_keyword_candidates")
    op.drop_index("ix_cie_keyword_candidates_run_id", table_name="cie_keyword_candidates")
    op.drop_table("cie_keyword_candidates")
    op.drop_index("ix_cie_keyword_runs_status", table_name="cie_keyword_runs")
    op.drop_index("ix_cie_keyword_runs_user_id", table_name="cie_keyword_runs")
    op.drop_index("ix_cie_keyword_runs_account_id", table_name="cie_keyword_runs")
    op.drop_index("ix_cie_keyword_runs_campaign_id", table_name="cie_keyword_runs")
    op.drop_table("cie_keyword_runs")
