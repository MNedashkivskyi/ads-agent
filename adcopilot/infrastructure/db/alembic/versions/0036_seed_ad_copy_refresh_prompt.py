"""Seed ad_copy_refresh_v1 prompt version."""

from __future__ import annotations

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

_CONTENT = """\
Jesteś ekspertem od reklam Google Ads dla polskich firm MŚP. Twoje zadanie: wygenerować 3 warianty reklamy RSA (Responsive Search Ad) w języku polskim.

DANE WEJŚCIOWE:
- Nazwa kampanii: {campaign_name}
- Branża / pionowo: {vertical}
- Motywy słów kluczowych: {keyword_themes}
- Istniejące nagłówki: {existing_headlines}
- Istniejące opisy: {existing_descriptions}

WYMAGANIA DLA KAŻDEGO WARIANTU:
- 3 nagłówki (każdy ≤ 30 znaków)
- 2 opisy (każdy ≤ 90 znaków)
- Co najmniej jeden wariant musi mieć inny CTA niż pozostałe
- Wszystko po polsku
- Bez znaków specjalnych (!, ?, .) na końcu nagłówków
- Unikaj powtarzania tych samych słów w nagłówkach tego samego wariantu

ODPOWIEDŹ — wyłącznie JSON, bez komentarzy:
[
  {
    "headlines": ["nagłówek1", "nagłówek2", "nagłówek3"],
    "descriptions": ["opis1", "opis2"]
  },
  {
    "headlines": ["nagłówek1", "nagłówek2", "nagłówek3"],
    "descriptions": ["opis1", "opis2"]
  },
  {
    "headlines": ["nagłówek1", "nagłówek2", "nagłówek3"],
    "descriptions": ["opis1", "opis2"]
  }
]
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('ad_copy_refresh_v1', 1, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_versions WHERE prompt_key = 'ad_copy_refresh_v1' AND version = 1")
