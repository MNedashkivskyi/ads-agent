"""Unit tests for client Q&A use case and API endpoint (Task 5.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient


def _jwt(user_id: str = "user-123") -> dict:
    from jose import jwt
    from adcopilot.config import get_settings
    token = jwt.encode({"sub": user_id}, get_settings().SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    from adcopilot.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


# --- Use case tests ---

@pytest.mark.asyncio
async def test_answer_returns_polish_text() -> None:
    from adcopilot.application.use_cases.answer_client_question import AnswerClientQuestionUseCase

    llm = AsyncMock()
    llm.complete.return_value = "CPA wynosi 12,50 zł na podstawie danych z ostatniego tygodnia."

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "Dane: {account_context}\nPytanie: {question}"
    prompt_repo.get_latest.return_value = pv

    use_case = AnswerClientQuestionUseCase(llm=llm, prompt_repo=prompt_repo)
    answer = await use_case.execute("Jaki jest mój CPA?", {"account_id": "acc-1", "summary": {"cpa_pln": 12.5}})

    assert "CPA" in answer or "zł" in answer
    llm.complete.assert_called_once()


@pytest.mark.asyncio
async def test_answer_strips_whitespace() -> None:
    from adcopilot.application.use_cases.answer_client_question import AnswerClientQuestionUseCase

    llm = AsyncMock()
    llm.complete.return_value = "  Odpowiedź z białymi znakami.  \n"

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "{account_context} {question}"
    prompt_repo.get_latest.return_value = pv

    use_case = AnswerClientQuestionUseCase(llm=llm, prompt_repo=prompt_repo)
    answer = await use_case.execute("Test", {})

    assert answer == "Odpowiedź z białymi znakami."


# --- API tests ---

def test_ask_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/user-123/ask", json={"question": "Jaki jest mój CPA?"})
    assert resp.status_code == 401


def test_ask_denies_wrong_user(client: TestClient) -> None:
    resp = client.post(
        "/api/user-123/ask",
        json={"question": "Jaki jest mój CPA?"},
        headers=_jwt("other"),
    )
    assert resp.status_code == 403


def test_ask_response_schema() -> None:
    from adcopilot.interfaces.api.qa import AskResponse
    r = AskResponse(
        answer="Twój CPA wynosi 12,50 zł.",
        context_summary={"account_id": "acc-1", "has_data": True},
    )
    assert r.answer.startswith("Twój")
    assert r.context_summary["has_data"] is True


def test_ask_request_rejects_empty_question() -> None:
    from pydantic import ValidationError
    from adcopilot.interfaces.api.qa import AskRequest
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_ask_request_rejects_too_long_question() -> None:
    from pydantic import ValidationError
    from adcopilot.interfaces.api.qa import AskRequest
    with pytest.raises(ValidationError):
        AskRequest(question="x" * 501)
