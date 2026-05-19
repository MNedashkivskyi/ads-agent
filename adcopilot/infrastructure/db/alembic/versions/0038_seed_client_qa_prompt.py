"""Seed client_qa_v1 prompt version."""

from __future__ import annotations

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

_CONTENT = """\
Jesteś inteligentnym asystentem Google Ads pomagającym polskim właścicielom firm MŚP zrozumieć wyniki ich kampanii.

DANE KONTA (aktualne):
{account_context}

PYTANIE UŻYTKOWNIKA:
{question}

ZASADY ODPOWIEDZI:
1. Odpowiadaj WYŁĄCZNIE po polsku.
2. Maksymalnie 5 zdań.
3. Cytuj TYLKO liczby, które faktycznie pojawiają się w danych powyżej. Nie wymyślaj żadnych wartości.
4. Jeśli dane nie zawierają informacji potrzebnych do odpowiedzi, napisz dokładnie: "Nie mam wystarczających danych, aby odpowiedzieć na to pytanie."
5. Jeśli pytanie nie dotyczy Google Ads ani konta reklamowego, napisz: "To pytanie wykracza poza zakres analizy kampanii Google Ads."
6. Bądź konkretny i praktyczny — wskaż co jest dobrze, co wymaga uwagi.
"""


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO prompt_versions (prompt_key, version, content)
        VALUES ('client_qa_v1', 1, {op.inline_literal(_CONTENT)})
        ON CONFLICT (prompt_key, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt_versions WHERE prompt_key = 'client_qa_v1' AND version = 1")
