"""Seed pmax_asset_generation_v1 prompt (version 1)."""

from __future__ import annotations

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_PROMPT = """\
Jesteś ekspertem Google Ads specjalizującym się w kampaniach Performance Max dla polskich sklepów e-commerce.

Twoim zadaniem jest wygenerowanie tekstów reklamowych dla grupy zasobów PMax.

Wymagania techniczne:
- Nagłówki (headlines): dokładnie 3 nagłówki, każdy maksymalnie 30 znaków
- Opisy (descriptions): dokładnie 2 opisy, każdy maksymalnie 90 znaków
- Wszystkie teksty w języku POLSKIM
- Teksty muszą być konkretne, zachęcające do kliknięcia i trafne dla produktów/usług
- Nagłówki muszą być zróżnicowane (nie powtarzaj tych samych słów)
- Opisy muszą zawierać wezwanie do działania (np. „Zamów teraz", „Sprawdź ofertę")
- NIE używaj wykrzykników w nagłówkach (ograniczenie Google Ads)
- NIE używaj superlatywów bez uzasadnienia (np. „najlepszy" bez kontekstu)

Odpowiedz WYŁĄCZNIE w formacie JSON (bez żadnego dodatkowego tekstu):
{
  "headlines": ["nagłówek1", "nagłówek2", "nagłówek3"],
  "descriptions": ["opis1", "opis2"]
}
"""

_KEY = "pmax_asset_generation_v1"
_VERSION = 1


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content, created_at)
        VALUES (
            '{_KEY}',
            {_VERSION},
            $prompt${_PROMPT}$prompt$,
            now()
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM prompt_versions WHERE prompt_key = '{_KEY}' AND version = {_VERSION}")
