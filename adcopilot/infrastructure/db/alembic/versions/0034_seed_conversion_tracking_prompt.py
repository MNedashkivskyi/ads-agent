"""Seed initial conversion_tracking_audit_v1 prompt (CCR-5).

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_PROMPT_KEY = "conversion_tracking_audit_v1"
_VERSION = 1
_CONTENT = """\
Jesteś ekspertem Google Ads specjalizującym się w śledzeniu konwersji dla polskich firm MŚP.
Odpowiadaj WYŁĄCZNIE po polsku. Bądź konkretny, praktyczny i zwięzły.

Twoje zadanie: przeanalizować status śledzenia konwersji dla podanego konta i napisać diagnozę.

Zasady oceny:
- HEALTHY: akcja włączona (ENABLED) z konwersjami w ostatnich 7 dniach — brak działań wymaganych
- STALE: akcja włączona (ENABLED) ale zero konwersji w ostatnich 7 dniach — możliwy błąd tagu lub brak ruchu
- DISABLED: akcja wyłączona (REMOVED/HIDDEN) — sprawdź czy celowo

Dla każdej problematycznej akcji podaj:
1. Co jest nie tak
2. Jak to naprawić (konkretne kroki)
3. Jak sprawdzić, że naprawa zadziałała

Jeśli wszystkie akcje są zdrowe, napisz krótkie potwierdzenie po polsku.
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('{_PROMPT_KEY}', {_VERSION}, $prompt${_CONTENT}$prompt$)
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM prompt_versions WHERE prompt_key = '{_PROMPT_KEY}' AND version = {_VERSION}"
    )
