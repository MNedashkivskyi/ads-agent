"""0052 - seed seasonality prompt version.

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO prompt_versions (prompt_key, content, version)
        VALUES (
            'seasonality_v1',
            'Napisz rekomendację sezonową w języku polskim dla konta Google Ads na podstawie poniższych danych. Wskaż konkretne daty, kwoty budżetu i działania do podjęcia.\n\nDane sezonowe:\n{seasonal_data}',
            1
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_versions WHERE prompt_key = 'seasonality_v1'")
