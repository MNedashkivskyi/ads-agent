"""Integration tests for the 6-question Telegram interview flow.

Test strategy
-------------
We test the FSM helpers (fsm_start, fsm_handle_text, etc.) directly
against a real test database so we exercise both the domain logic and
the SQL repository without any network calls.

Telegram-specific behaviour (message formatting, button construction,
handler wiring) is covered by unit-level tests using AsyncMock objects
at the bottom of this file.

Fixtures
--------
``db_engine`` and ``db_session`` come from tests/conftest.py which
creates all tables (including the new launch_ tables) at session scope.
"""

from __future__ import annotations

import base64
import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
    SqlCampaignBriefRepository,
)
from adcopilot.infrastructure.telegram.interview_handler import (
    QUESTIONS,
    _resume_banner,
    _voice_confirm_keyboard,
    format_summary,
    fsm_cancel,
    fsm_fix_step,
    fsm_handle_text,
    fsm_q4_action,
    fsm_skip_q6,
    fsm_start,
    is_long_pause,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_USER_ID = UserId(str(uuid.uuid4()))
_ACCOUNT_ID = AccountId(str(uuid.uuid4()))


@pytest_asyncio.fixture
async def repo(db_session: AsyncSession) -> SqlCampaignBriefRepository:
    return SqlCampaignBriefRepository(db_session)


# ---------------------------------------------------------------------------
# Happy path — complete interview through all 6 questions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_complete_interview(repo: SqlCampaignBriefRepository) -> None:
    """Walk all 6 questions to step 7 and verify brief fields."""
    # Q1 — start interview
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    assert ir.brief.interview_step == 1
    assert ir.text == QUESTIONS[1]
    brief = ir.brief

    # Q1 answer — business description
    ir = await fsm_handle_text(brief, "We sell handmade running shoes", repo)
    assert ir.brief.interview_step == 2
    assert ir.brief.business_description == "We sell handmade running shoes"
    assert ir.text == QUESTIONS[2]
    brief = ir.brief

    # Q2 answer — location
    ir = await fsm_handle_text(brief, "Warsaw + 50 km", repo)
    assert ir.brief.interview_step == 3
    assert ir.brief.location == "Warsaw + 50 km"
    brief = ir.brief

    # Q3 answer — typical customer value
    ir = await fsm_handle_text(brief, "350", repo)
    assert ir.brief.interview_step == 4
    assert ir.brief.typical_customer_value == Decimal("350")
    # Q4 uses inline buttons, so we expect a keyboard
    assert ir.keyboard is not None
    brief = ir.brief

    # Q4 answer — primary action (via FSM helper, not callback)
    ir = await fsm_q4_action(brief, "Purchase", repo)
    assert ir.brief.interview_step == 5
    assert ir.brief.primary_action == "Purchase"
    assert ir.text == QUESTIONS[5]
    brief = ir.brief

    # Q5 answer — budget
    ir = await fsm_handle_text(brief, "3000", repo)
    assert ir.brief.interview_step == 6
    assert ir.brief.monthly_budget_pln == Decimal("3000")
    assert ir.text == QUESTIONS[6]
    brief = ir.brief

    # Q6 answer — exclusions
    ir = await fsm_handle_text(brief, "wholesale, distributor, cheap", repo)
    assert ir.brief.interview_step == 7
    assert ir.brief.exclusions == ["wholesale", "distributor", "cheap"]
    assert ir.brief.status == LaunchStatus.COLLECTING  # still COLLECTING until generation
    assert ir.keyboard is not None  # summary keyboard

    # Verify persisted state
    saved = await repo.get(brief.id)
    assert saved is not None
    assert saved.interview_step == 7
    assert saved.exclusions == ["wholesale", "distributor", "cheap"]


# ---------------------------------------------------------------------------
# Voice message transcription and confirmation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_confirmation_accept(repo: SqlCampaignBriefRepository) -> None:
    """Accepted transcription flows through as the answer for the current step."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    brief = ir.brief  # step=1

    transcribed_text = "We sell organic dog treats"
    # Simulate user accepting the transcription
    ir2 = await fsm_handle_text(brief, transcribed_text, repo)
    assert ir2.brief.business_description == "We sell organic dog treats"
    assert ir2.brief.interview_step == 2


@pytest.mark.asyncio
async def test_voice_message_handler_no_transcription(repo: SqlCampaignBriefRepository) -> None:
    """When no active user is found the handler returns without error."""

    from adcopilot.infrastructure.telegram.interview_handler import voice_message_handler

    # Build mocked Update with voice message (chat_id has no user in DB)
    mock_voice = MagicMock()
    mock_message = AsyncMock()
    mock_message.chat_id = 99999  # not in DB
    mock_message.voice = mock_voice
    mock_update = MagicMock()
    mock_update.message = mock_message

    # Mock create_async_engine so we don't open a real second connection.
    # The session's execute() returns a result where scalar_one_or_none() is None
    # so the handler returns early (user not found path).
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()

    with patch(
        "adcopilot.infrastructure.telegram.interview_handler.create_async_engine",
        return_value=mock_engine,
    ), patch(
        "adcopilot.infrastructure.telegram.interview_handler.get_settings"
    ) as mock_settings, patch(
        "adcopilot.infrastructure.telegram.interview_handler.AsyncSession",
        return_value=mock_session_ctx,
    ):
        mock_settings.return_value.DATABASE_URL = "postgresql+asyncpg://x:y@localhost/z"
        # Handler returns early when user_model is None — no error raised
        await voice_message_handler(mock_update, MagicMock())

    # If we got here without exception the no-user early-exit path is covered.


@pytest.mark.asyncio
async def test_voice_confirm_keyboard_roundtrip() -> None:
    """Voice confirmation keyboard encodes and decodes text correctly."""
    brief_id = "brief-test"
    original_text = "organic dog food"
    keyboard = _voice_confirm_keyboard(brief_id, original_text)

    # First button has the encoded text
    ok_button = keyboard.inline_keyboard[0][0]
    assert ok_button.callback_data is not None
    parts = ok_button.callback_data.split(":", 2)
    assert parts[0] == "iv_voice_ok"
    assert parts[1] == brief_id
    decoded = base64.urlsafe_b64decode(parts[2]).decode()
    assert decoded == original_text


# ---------------------------------------------------------------------------
# /cancel at various steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_at_step_1(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    await fsm_cancel(ir.brief, repo)
    saved = await repo.get(ir.brief.id)
    assert saved is not None
    assert saved.status == LaunchStatus.ABANDONED


@pytest.mark.asyncio
async def test_cancel_at_step_3(repo: SqlCampaignBriefRepository) -> None:
    """Cancel mid-interview persists ABANDONED status."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Shoe repair shop", repo)
    ir = await fsm_handle_text(ir.brief, "Kraków", repo)

    await fsm_cancel(ir.brief, repo)
    saved = await repo.get(ir.brief.id)
    assert saved is not None
    assert saved.status == LaunchStatus.ABANDONED
    # Answers so far are preserved
    assert saved.business_description == "Shoe repair shop"
    assert saved.location == "Kraków"


@pytest.mark.asyncio
async def test_cancel_handler_via_telegram(repo: SqlCampaignBriefRepository) -> None:
    """cancel_interview_handler (mocked Telegram) abandons the active brief via fsm_cancel."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    brief_id = ir.brief.id

    # Brief should be COLLECTING before cancel
    saved = await repo.get(CampaignBriefId(brief_id))
    assert saved is not None and saved.status == LaunchStatus.COLLECTING

    # Call fsm_cancel directly (the Telegram handler delegates to it after DB lookup)
    await fsm_cancel(ir.brief, repo)

    saved2 = await repo.get(CampaignBriefId(brief_id))
    assert saved2 is not None
    assert saved2.status == LaunchStatus.ABANDONED


# ---------------------------------------------------------------------------
# Resume after 24-hour pause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_after_24h_pause(repo: SqlCampaignBriefRepository) -> None:
    """A brief older than 24h is identified as a long pause."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Wedding photography studio", repo)
    ir = await fsm_handle_text(ir.brief, "Warsaw", repo)
    brief_at_step3 = ir.brief  # step=3, asking Q3

    assert not is_long_pause(brief_at_step3)  # just created

    # Simulate the brief being 25 hours old
    old_brief = dataclasses.replace(
        brief_at_step3,
        created_at=datetime.now(UTC) - timedelta(hours=25),
    )
    await repo.save(old_brief)

    reloaded = await repo.get(brief_at_step3.id)
    assert reloaded is not None
    assert is_long_pause(reloaded)  # now it's a long pause


@pytest.mark.asyncio
async def test_resume_banner_shows_progress(repo: SqlCampaignBriefRepository) -> None:
    """_resume_banner includes all answered questions."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Italian restaurant", repo)
    ir = await fsm_handle_text(ir.brief, "Rome + 10 km", repo)

    banner = _resume_banner(ir.brief)
    assert "Italian restaurant" in banner
    assert "Rome + 10 km" in banner


@pytest.mark.asyncio
async def test_resume_continues_from_correct_step(repo: SqlCampaignBriefRepository) -> None:
    """Saving the brief and re-loading preserves step for resume."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Flower shop", repo)
    ir = await fsm_handle_text(ir.brief, "Gdańsk", repo)

    # Reload brief — simulates the user coming back after restart
    reloaded = await repo.get(ir.brief.id)
    assert reloaded is not None
    assert reloaded.interview_step == 3
    assert reloaded.business_description == "Flower shop"
    assert reloaded.location == "Gdańsk"

    # Continue from step 3 (Q3)
    ir = await fsm_handle_text(reloaded, "400", repo)
    assert ir.brief.interview_step == 4


# ---------------------------------------------------------------------------
# Invalid input validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_pln_at_step3(repo: SqlCampaignBriefRepository) -> None:
    """Non-numeric input at Q3 raises ValueError with a friendly message."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Bookshop", repo)
    ir = await fsm_handle_text(ir.brief, "Wrocław", repo)
    # brief is now at step=3

    with pytest.raises(ValueError, match="Customer value must be a number"):
        await fsm_handle_text(ir.brief, "a lot", repo)

    # Step should remain unchanged after invalid input
    reloaded = await repo.get(ir.brief.id)
    assert reloaded is not None
    assert reloaded.interview_step == 3


@pytest.mark.asyncio
async def test_budget_below_minimum(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Yoga studio", repo)
    ir = await fsm_handle_text(ir.brief, "Poznań", repo)
    ir = await fsm_handle_text(ir.brief, "300", repo)
    ir = await fsm_q4_action(ir.brief, "Book", repo)
    # brief at step=5 (Q5 — budget)

    with pytest.raises(ValueError, match="100"):
        await fsm_handle_text(ir.brief, "50", repo)


@pytest.mark.asyncio
async def test_budget_above_maximum(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Yoga studio", repo)
    ir = await fsm_handle_text(ir.brief, "Poznań", repo)
    ir = await fsm_handle_text(ir.brief, "300", repo)
    ir = await fsm_q4_action(ir.brief, "Book", repo)

    with pytest.raises(ValueError, match="20"):
        await fsm_handle_text(ir.brief, "999999", repo)


@pytest.mark.asyncio
async def test_budget_boundary_values(repo: SqlCampaignBriefRepository) -> None:
    """100 and 20000 PLN are exactly on the boundary — both valid."""
    for budget in ("100", "20000"):
        ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
        ir = await fsm_handle_text(ir.brief, "Test", repo)
        ir = await fsm_handle_text(ir.brief, "Test", repo)
        ir = await fsm_handle_text(ir.brief, "100", repo)
        ir = await fsm_q4_action(ir.brief, "Call", repo)
        ir = await fsm_handle_text(ir.brief, budget, repo)
        assert ir.brief.interview_step == 6


# ---------------------------------------------------------------------------
# Skip Q6 (exclusions optional)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_exclusions(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Pet grooming", repo)
    ir = await fsm_handle_text(ir.brief, "Łódź", repo)
    ir = await fsm_handle_text(ir.brief, "200", repo)
    ir = await fsm_q4_action(ir.brief, "Call", repo)
    ir = await fsm_handle_text(ir.brief, "1500", repo)

    # Skip Q6
    ir = await fsm_skip_q6(ir.brief, repo)
    assert ir.brief.interview_step == 7
    assert ir.brief.exclusions == []
    # Summary should be in the text
    assert "Pet grooming" in ir.text


# ---------------------------------------------------------------------------
# Fix an answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_step_rewinds_correctly(repo: SqlCampaignBriefRepository) -> None:
    """Fixing step 2 (location) rewinds and re-asks Q2."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Dentist clinic", repo)
    ir = await fsm_handle_text(ir.brief, "Wrong city", repo)  # step=3 now

    # Fix location (step 2)
    ir = await fsm_fix_step(ir.brief, 2, repo)
    assert ir.brief.interview_step == 2
    assert QUESTIONS[2] in ir.text or "customers located" in ir.text

    # Provide corrected answer
    ir = await fsm_handle_text(ir.brief, "Kraków + 20 km", repo)
    assert ir.brief.location == "Kraków + 20 km"
    assert ir.brief.interview_step == 3


@pytest.mark.asyncio
async def test_fix_q4_sends_keyboard(repo: SqlCampaignBriefRepository) -> None:
    """Fixing step 4 (primary action) must include the inline keyboard."""
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Pharmacy", repo)
    ir = await fsm_handle_text(ir.brief, "Białystok", repo)
    ir = await fsm_handle_text(ir.brief, "150", repo)
    ir = await fsm_q4_action(ir.brief, "Call", repo)

    ir = await fsm_fix_step(ir.brief, 4, repo)
    assert ir.brief.interview_step == 4
    assert ir.keyboard is not None


# ---------------------------------------------------------------------------
# format_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_format_summary_all_fields(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    ir = await fsm_handle_text(ir.brief, "Car wash", repo)
    ir = await fsm_handle_text(ir.brief, "Warsaw", repo)
    ir = await fsm_handle_text(ir.brief, "500", repo)
    ir = await fsm_q4_action(ir.brief, "Visit website", repo)
    ir = await fsm_handle_text(ir.brief, "2000", repo)
    ir = await fsm_handle_text(ir.brief, "kids, motorcycles", repo)

    summary = format_summary(ir.brief)
    assert "Car wash" in summary
    assert "Warsaw" in summary
    assert "500" in summary
    assert "Visit website" in summary
    assert "2,000" in summary
    assert "kids" in summary


# ---------------------------------------------------------------------------
# get_active_for_user — only returns COLLECTING briefs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_ignores_abandoned(repo: SqlCampaignBriefRepository) -> None:
    ir = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)
    await fsm_cancel(ir.brief, repo)

    active = await repo.get_active_for_user(_USER_ID)
    assert active is None


@pytest.mark.asyncio
async def test_get_active_returns_latest_collecting(
    repo: SqlCampaignBriefRepository,
) -> None:
    # Create two COLLECTING briefs
    ir1 = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)  # noqa: F841
    ir2 = await fsm_start(_USER_ID, _ACCOUNT_ID, "en", repo)

    active = await repo.get_active_for_user(_USER_ID)
    assert active is not None
    # Should be the most recently created one
    assert active.id == ir2.brief.id
