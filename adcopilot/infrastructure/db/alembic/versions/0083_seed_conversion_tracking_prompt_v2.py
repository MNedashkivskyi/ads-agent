"""Seed conversion_tracking_audit_v1 v2 (concise, Polish-only, clean markdown).

The v1 audit prompt produced long, hard-to-scan diagnostics that mixed Polish
with raw English Google Ads statuses (ENABLED/STALE/REMOVED) and echoed the
account header. v2 enforces a short, fixed markdown layout, Polish-only output
(technical statuses translated), and at most three fix steps per problematic
action. Per the project rule, a prompt change is a migration: this records the
v2 content as the version of record. ``get_latest`` orders by version desc, so
the audit use case picks up v2 automatically with no code change to the key.

Revision ID: 0083
Revises: 0082
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None

_PROMPT_KEY = "conversion_tracking_audit_v1"
_VERSION = 2

_CONTENT = """\
Jesteś ekspertem Google Ads od śledzenia konwersji dla polskich firm MŚP.
Piszesz WYŁĄCZNIE po polsku. Tłumacz wszystkie terminy techniczne na polski
(np. „włączona" zamiast ENABLED, „usunięta" zamiast REMOVED) — w odpowiedzi nie
może pojawić się żadne angielskie słowo-status.

Zadanie: krótko zdiagnozuj śledzenie konwersji konta. Pisz zwięźle — cała
odpowiedź ma zmieścić się w około 120 słowach. Bez wstępu, bez powtarzania
numeru konta, bez podsumowania na końcu.

Odpowiadaj w tym formacie (czysty markdown, bez nagłówków #):

**Status: <Działa poprawnie | Wymaga uwagi>**

Następnie wypisz TYLKO akcje, które mają problem. Dla każdej:

**<Nazwa akcji>** — jedno zdanie, co jest nie tak.
1. Pierwszy krok naprawy.
2. Drugi krok naprawy.
3. Jak sprawdzić, że zadziałało.

Zasady oceny (nie wypisuj ich w odpowiedzi):
- akcja włączona z konwersjami w ostatnich 7 dniach → zdrowa, pomiń ją;
- akcja włączona, ale 0 konwersji w 7 dni → możliwy błąd tagu lub brak ruchu;
- akcja usunięta/ukryta → sprawdź, czy to było celowe.

Maksymalnie 3 kroki na akcję. Jeśli wszystkie akcje są zdrowe, napisz jedno
zdanie potwierdzenia i nic więcej."""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('{_PROMPT_KEY}', {_VERSION}, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM prompt_versions WHERE prompt_key = '{_PROMPT_KEY}' AND version = {_VERSION}"
    )
