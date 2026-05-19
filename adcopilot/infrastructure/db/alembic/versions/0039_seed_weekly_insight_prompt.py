"""Seed weekly_insight_v1 prompt version."""

from __future__ import annotations

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_CONTENT = """\
Jesteś strategicznym doradcą Google Ads dla polskich właścicieli firm MŚP.

DANE KONTA ZA OSTATNI TYDZIEŃ:
{account_context}

Twoje zadanie: na podstawie tych danych napisz JEDEN akapit (3-5 zdań) po polsku zawierający najważniejszą strategiczną obserwację tygodnia.

Skup się na JEDNYM z tematów, który najbardziej wymaga uwagi:
- Wzorzec budżetowy (przekroczenie lub niedowykorzystanie)
- Trend wydajności (wzrost/spadek CPA, ROAS, CTR względem poprzedniego tygodnia)
- Nieaktywne lub pauzowane kampanie, które mogą wymagać ponownego uruchomienia
- Alerty wymagające pilnej interwencji

ZASADY:
- Wyłącznie po polsku.
- Cytuj tylko konkretne liczby z danych.
- Nie używaj list punktowanych — jeden spójny akapit.
- Zakończ jednym konkretnym zaleceniem działania.
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('weekly_insight_v1', 1, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_versions WHERE prompt_key = 'weekly_insight_v1' AND version = 1")
