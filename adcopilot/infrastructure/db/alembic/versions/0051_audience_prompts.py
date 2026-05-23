"""0051 - seed audience strategy and custom intent prompt versions.

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO prompt_versions (prompt_key, content, version)
        VALUES (
            'audience_strategy_v1',
            'Przeanalizuj poniższe dane o wydajności grup odbiorców Google Ads i napisz 3–5 konkretnych rekomendacji strategicznych w języku polskim. Skup się na: (1) grupach odbiorców wartych zwiększenia stawki, (2) grupach wartych zmniejszenia stawki lub wykluczenia, (3) możliwościach rozszerzenia zasięgu.\n\nDane:\n{audience_context}',
            1
        )
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO prompt_versions (prompt_key, content, version)
        VALUES (
            'custom_intent_v1',
            'Pogrupuj poniższe frazy wyszukiwania w klastry tematyczne (max 5 klastrów). Dla każdego klastra podaj: nazwę (max 5 słów) i listę fraz. Następnie napisz krótką rekomendację (2–3 zdania) jak wykorzystać te klastry w niestandardowych listach odbiorców Google Ads.\n\nOdpowiedz w formacie JSON:\n{{"clusters": [{{"name": "...", "terms": ["..."]}}], "recommendations_pl": "..."}}\n\nFrazy:\n{search_terms}',
            1
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM prompt_versions WHERE prompt_key IN ('audience_strategy_v1', 'custom_intent_v1')"
    )
