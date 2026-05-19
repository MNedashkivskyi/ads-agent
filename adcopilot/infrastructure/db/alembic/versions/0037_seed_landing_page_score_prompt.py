"""Seed landing_page_score_v1 prompt version."""

from __future__ import annotations

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_CONTENT = """\
Jesteś ekspertem UX i SEO pomagającym polskim właścicielom firm MŚP poprawić ich strony docelowe dla reklam Google Ads.

Poniżej znajdziesz wyniki audytu PageSpeed Insights dla strony:
URL: {url}
Wynik wydajności: {performance_score}/100
Wynik dostępności: {accessibility_score}/100
Wynik SEO: {seo_score}/100
Dobre praktyki: {best_practices_score}/100
Przyjazność dla urządzeń mobilnych: {mobile_friendly}
LCP (Largest Contentful Paint): {lcp_ms}
FCP (First Contentful Paint): {fcp_ms}
CLS (Cumulative Layout Shift): {cls_score}
TBT (Total Blocking Time): {tbt_ms}
TTFB (Time to First Byte): {ttfb_ms}

Na podstawie tych wyników wygeneruj DOKŁADNIE 3 konkretne rekomendacje poprawy w języku polskim.
Każda rekomendacja powinna:
1. Zidentyfikować konkretny problem (np. zbyt duże obrazy, brak atrybutu alt, brak metatytułu)
2. Wyjaśnić jego wpływ na wyniki reklamowe i jakość kampanii Google Ads
3. Podać konkretny krok naprawczy możliwy do wykonania przez właściciela MŚP

ODPOWIEDŹ — wyłącznie JSON, bez komentarzy:
["rekomendacja 1", "rekomendacja 2", "rekomendacja 3"]
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('landing_page_score_v1', 1, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_versions WHERE prompt_key = 'landing_page_score_v1' AND version = 1")
