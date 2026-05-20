"""0050 - performance_reports table.

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_reports",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "report_data",
            JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("summary_pl", sa.Text(), nullable=True),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_performance_reports_user_id", "performance_reports", ["user_id"])
    op.create_index("ix_performance_reports_account_id", "performance_reports", ["account_id"])

    op.execute(
        """
        INSERT INTO prompt_versions (prompt_key, content, version, is_active)
        VALUES (
            'performance_report_v1',
            'Napisz 2-akapitowy raport zarzadczy w jezyku polskim na podstawie ponizszych danych konta Google Ads. Akapit 1: wyniki vs poprzedni okres. Akapit 2: najwazniejsze dzialania i rekomendacje na nastepny miesiac.\n\nDane:\n{account_context}',
            1,
            true
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_performance_reports_account_id", table_name="performance_reports")
    op.drop_index("ix_performance_reports_user_id", table_name="performance_reports")
    op.drop_table("performance_reports")
