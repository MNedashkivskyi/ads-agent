"""Telegram handlers for the 6-question campaign-launch interview flow.

Architecture
------------
The interview is driven by a *finite-state machine* (FSM) encoded as the
``interview_step`` field on the ``CampaignBrief`` aggregate:

  step 0 – brief just created, will ask Q1 on next interaction
  step 1 – waiting for answer to Q1 (business description)
  step 2 – Q1 answered, waiting for Q2 (location)
  step 3 – Q2 answered, waiting for Q3 (customer value, PLN)
  step 4 – Q3 answered, waiting for Q4 (primary action — inline button)
  step 5 – Q4 answered, waiting for Q5 (monthly budget, PLN 100–20 000)
  step 6 – Q5 answered, waiting for Q6 (exclusions — optional, /skip)
  step 7 – all questions answered, summary shown

Each of the FSM transition helpers is a *pure* async function that takes
the current brief + raw user input and returns an ``InterviewResult``
(updated brief + reply text + optional keyboard).  Handlers at the bottom
of this module are thin Telegram glue on top of those helpers.

State persistence
-----------------
The brief is saved to the database *before* sending the reply, so a
crash between the DB write and the Telegram send will prompt the user to
resend their answer — safe and idempotent.

Resume
------
If the user stops responding and comes back later, ``fallback_handler``
(in handlers.py) detects the active COLLECTING brief and re-sends the
current question.  A 24-hour gap triggers a "Welcome back!" banner.
"""

from __future__ import annotations

import dataclasses
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adcopilot.config import get_settings
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.launch.entities import (
    CampaignBrief,
    CampaignBriefId,
    LaunchStatus,
)
from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
    SqlCampaignBriefRepository,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Vertical detection helpers
# ---------------------------------------------------------------------------

# Maps detect_vertical_from_description output → Polish market benchmark key
_VERTICAL_TO_POLISH: dict[str, str] = {
    "salon": "salon",
    "ecommerce": "e-commerce",
    "restaurant": "restauracja",
    "legal": "prawnik",
    "medical": "lekarz",
    "nieruchomości": "nieruchomości",
    "edukacja": "edukacja",
    "usługi domowe": "usługi domowe",
}


def _detect_vertical(business_description: str) -> str | None:
    """Return Polish market vertical key for *business_description*, or None."""
    try:
        from adcopilot.domain.launch.templates import detect_vertical_from_description
        raw = detect_vertical_from_description(business_description)
        return _VERTICAL_TO_POLISH.get(raw)
    except Exception:
        return None


def _check_budget_warning(vertical: str | None, location: str, budget: "Decimal") -> str:
    """Return a non-empty warning string if budget is below the Polish market minimum."""
    from adcopilot.domain.polish_market.budget_validator import validate_budget
    if not location:
        return ""
    effective_vertical = vertical or ""
    result = validate_budget(effective_vertical, location, budget)
    if result.warning_message:
        logger.info(
            "budget_warning_shown",
            vertical=effective_vertical,
            location=location,
            budget=str(budget),
        )
        return "\n\n⚠️ " + result.warning_message
    return ""

# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------

QUESTIONS: dict[int, str] = {
    1: "What does your business sell or offer? 🏪",
    2: "Where are your customers located?\n(e.g. Warsaw, Warsaw + 30 km, or Poland) 📍",
    3: "What is a typical customer worth to you in revenue?\n(enter PLN amount, e.g. 500) 💰",
    4: "What action do you want someone to take after seeing your ad? 👇",
    5: "What's your monthly budget for ads?\n(PLN amount, 100–20 000) 💵",
    6: "Anything specific you DON'T want your ad shown for?\n(optional — type exclusions or send /skip) 🚫",
}

PRIMARY_ACTIONS = ["Call", "Book", "Purchase", "Visit website", "Sign up"]

BUDGET_MIN = Decimal("100")
BUDGET_MAX = Decimal("20000")

# ---------------------------------------------------------------------------
# FSM result type
# ---------------------------------------------------------------------------


class InterviewResult(NamedTuple):
    brief: CampaignBrief
    text: str
    keyboard: InlineKeyboardMarkup | None = None


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def _primary_action_keyboard(brief_id: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(action, callback_data=f"iv_q4:{brief_id}:{action}")
        for action in PRIMARY_ACTIONS
    ]
    # Two rows: 3 + 2
    return InlineKeyboardMarkup([buttons[:3], buttons[3:]])


def _summary_keyboard(brief_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Generate my campaign", callback_data=f"iv_generate:{brief_id}"
                ),
                InlineKeyboardButton(
                    "✏️ Fix an answer", callback_data=f"iv_fix:{brief_id}"
                ),
            ]
        ]
    )


def _fix_keyboard(brief_id: str) -> InlineKeyboardMarkup:
    labels = {
        1: "1. Business",
        2: "2. Location",
        3: "3. Value",
        4: "4. Goal",
        5: "5. Budget",
        6: "6. Exclusions",
    }
    buttons = [
        InlineKeyboardButton(label, callback_data=f"iv_fix_q:{brief_id}:{step}")
        for step, label in labels.items()
    ]
    return InlineKeyboardMarkup([buttons[:3], buttons[3:]])


def _voice_confirm_keyboard(brief_id: str, text: str) -> InlineKeyboardMarkup:
    import base64

    # Encode text in base64 so it's safe for callback_data (max 64 bytes)
    encoded = base64.urlsafe_b64encode(text[:40].encode()).decode()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, that's right",
                    callback_data=f"iv_voice_ok:{brief_id}:{encoded}",
                ),
                InlineKeyboardButton(
                    "✏️ No, let me retype",
                    callback_data=f"iv_voice_no:{brief_id}",
                ),
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Summary formatter
# ---------------------------------------------------------------------------


def format_summary(brief: CampaignBrief) -> str:
    exclusions_text = ", ".join(brief.exclusions) if brief.exclusions else "None"
    return (
        "📋 *Your campaign brief:*\n\n"
        f"1️⃣ *Business:* {brief.business_description}\n"
        f"2️⃣ *Location:* {brief.location}\n"
        f"3️⃣ *Customer value:* {brief.typical_customer_value:,.0f} PLN\n"
        f"4️⃣ *Goal:* {brief.primary_action}\n"
        f"5️⃣ *Monthly budget:* {brief.monthly_budget_pln:,.0f} PLN\n"
        f"6️⃣ *Exclusions:* {exclusions_text}\n\n"
        "Ready to generate your campaign?"
    )


# ---------------------------------------------------------------------------
# Core FSM helpers (pure business logic — no Telegram API calls)
# ---------------------------------------------------------------------------


async def fsm_start(
    user_id: UserId,
    account_id: AccountId,
    language: str,
    repo: SqlCampaignBriefRepository,
) -> InterviewResult:
    """Create a new CampaignBrief (step 1) and return the first question."""
    from datetime import UTC, datetime

    brief = CampaignBrief(
        id=CampaignBriefId(str(uuid.uuid4())),
        user_id=user_id,
        account_id=account_id,
        business_description="",
        location="",
        typical_customer_value=Decimal("0"),
        primary_action="",
        monthly_budget_pln=Decimal("0"),
        exclusions=[],
        language=language,
        created_at=datetime.now(UTC),
        status=LaunchStatus.COLLECTING,
        interview_step=1,
    )
    await repo.save(brief)
    return InterviewResult(brief=brief, text=QUESTIONS[1])


async def fsm_handle_text(
    brief: CampaignBrief,
    text: str,
    repo: SqlCampaignBriefRepository,
) -> InterviewResult:
    """Process a free-text answer for the current step.

    Returns the updated brief + the next prompt.
    Raises ``ValueError`` with a user-friendly message on invalid input.
    """
    step = brief.interview_step

    if step == 1:
        description = text.strip()
        detected_vertical = _detect_vertical(description)
        updated = dataclasses.replace(
            brief,
            business_description=description,
            interview_step=2,
            vertical=detected_vertical,
        )
        await repo.save(updated)
        return InterviewResult(brief=updated, text=QUESTIONS[2])

    if step == 2:
        updated = dataclasses.replace(brief, location=text.strip(), interview_step=3)
        await repo.save(updated)
        return InterviewResult(brief=updated, text=QUESTIONS[3])

    if step == 3:
        value = _parse_pln(text, "Customer value")
        updated = dataclasses.replace(
            brief, typical_customer_value=value, interview_step=4
        )
        await repo.save(updated)
        keyboard = _primary_action_keyboard(brief.id)
        return InterviewResult(brief=updated, text=QUESTIONS[4], keyboard=keyboard)

    if step == 4:
        # Text answer for Q4 (user typed instead of tapping button)
        action = _match_primary_action(text)
        updated = dataclasses.replace(brief, primary_action=action, interview_step=5)
        await repo.save(updated)
        return InterviewResult(brief=updated, text=QUESTIONS[5])

    if step == 5:
        budget = _parse_pln(text, "Budget")
        if budget < BUDGET_MIN or budget > BUDGET_MAX:
            raise ValueError(
                f"Budget must be between {BUDGET_MIN:,.0f} and {BUDGET_MAX:,.0f} PLN. "
                f"You entered {budget:,.0f} PLN — please try again."
            )
        updated = dataclasses.replace(
            brief, monthly_budget_pln=budget, interview_step=6
        )
        await repo.save(updated)
        warning_text = _check_budget_warning(updated.vertical, updated.location, budget)
        return InterviewResult(brief=updated, text=QUESTIONS[6] + warning_text)

    if step == 6:
        # Q6 is optional; /skip handled separately
        exclusions = [x.strip() for x in re.split(r"[,;]", text) if x.strip()]
        updated = dataclasses.replace(
            brief, exclusions=exclusions, interview_step=7
        )
        await repo.save(updated)
        summary = format_summary(updated)
        keyboard = _summary_keyboard(brief.id)
        return InterviewResult(brief=updated, text=summary, keyboard=keyboard)

    if step == 7:
        # Summary already shown — nudge user to use the buttons
        keyboard = _summary_keyboard(brief.id)
        return InterviewResult(
            brief=brief,
            text="Please use the buttons above to generate your campaign or fix an answer.",
            keyboard=keyboard,
        )

    # step == 0 or unexpected: re-start from Q1
    updated = dataclasses.replace(brief, interview_step=1)
    await repo.save(updated)
    return InterviewResult(brief=updated, text=QUESTIONS[1])


async def fsm_skip_q6(
    brief: CampaignBrief,
    repo: SqlCampaignBriefRepository,
) -> InterviewResult:
    """Handle /skip at step 6 (exclusions are optional)."""
    updated = dataclasses.replace(brief, exclusions=[], interview_step=7)
    await repo.save(updated)
    summary = format_summary(updated)
    keyboard = _summary_keyboard(brief.id)
    return InterviewResult(brief=updated, text=summary, keyboard=keyboard)


async def fsm_q4_action(
    brief: CampaignBrief,
    action: str,
    repo: SqlCampaignBriefRepository,
) -> InterviewResult:
    """Handle Q4 inline-button answer (primary action)."""
    updated = dataclasses.replace(brief, primary_action=action, interview_step=5)
    await repo.save(updated)
    return InterviewResult(brief=updated, text=QUESTIONS[5])


async def fsm_cancel(
    brief: CampaignBrief,
    repo: SqlCampaignBriefRepository,
) -> None:
    """Abandon the interview — mark brief as ABANDONED."""
    updated = dataclasses.replace(brief, status=LaunchStatus.ABANDONED)
    await repo.save(updated)


async def fsm_fix_step(
    brief: CampaignBrief,
    target_step: int,
    repo: SqlCampaignBriefRepository,
) -> InterviewResult:
    """Rewind the interview to re-collect answer for *target_step*."""
    updated = dataclasses.replace(brief, interview_step=target_step)
    await repo.save(updated)
    if target_step == 4:
        keyboard = _primary_action_keyboard(brief.id)
        return InterviewResult(brief=updated, text=QUESTIONS[4], keyboard=keyboard)
    return InterviewResult(brief=updated, text=QUESTIONS[target_step])


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def _parse_pln(text: str, label: str) -> Decimal:
    """Parse a PLN amount from free text.  Raises ValueError on bad input."""
    cleaned = text.strip().replace(",", ".").replace(" ", "").replace("PLN", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(  # noqa: B904
            f"{label} must be a number (e.g. 500 or 1500.50). "
            f"I couldn't understand '{text}' — please try again."
        )


def _match_primary_action(text: str) -> str:
    """Map free-text answer to a PRIMARY_ACTIONS entry (case-insensitive)."""
    text_lower = text.strip().lower()
    for action in PRIMARY_ACTIONS:
        if action.lower() in text_lower or text_lower in action.lower():
            return action
    # Fall back to verbatim input (trimmed)
    return text.strip()


# ---------------------------------------------------------------------------
# Session factory (injectable for tests)
# ---------------------------------------------------------------------------


async def _make_session() -> AsyncSession:

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    return AsyncSession(engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Telegram callback handlers
# ---------------------------------------------------------------------------


async def interview_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route all iv_* callback_data strings to the appropriate FSM method."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    data = query.data  # e.g. "iv_start:acc-123" or "iv_q4:brief-1:Call"
    telegram_chat_id = query.from_user.id if query.from_user else None
    if telegram_chat_id is None:
        return

    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    # brief_id to dispatch a generation task for, set inside the session block
    generate_brief_id: str | None = None
    try:
        async with AsyncSession(engine) as session, session.begin():
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import UserModel

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == telegram_chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await query.answer("Please link your account first with /start.", show_alert=True)
                return

            user_id = UserId(str(user_model.id))
            repo = SqlCampaignBriefRepository(session)

            # ── iv_start:{account_id} ────────────────────────────────────────
            if data.startswith("iv_start:"):
                account_id = AccountId(data.split(":", 1)[1])
                result_ir = await fsm_start(
                    user_id, account_id, user_model.language or "pl", repo
                )
                await _send_result(query, result_ir, edit=False)

            # ── iv_q4:{brief_id}:{action} ─────────────────────────────────────
            elif data.startswith("iv_q4:"):
                _, brief_id_str, action = data.split(":", 2)
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if brief and brief.user_id == user_id and brief.status == LaunchStatus.COLLECTING:
                    result_ir = await fsm_q4_action(brief, action, repo)
                    await _send_result(query, result_ir, edit=True)

            # ── iv_generate:{brief_id} ────────────────────────────────────────
            elif data.startswith("iv_generate:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if brief and brief.user_id == user_id:
                    # --- PMax eligibility check (best-effort, e-commerce only) ---
                    try:
                        from adcopilot.application.use_cases.detect_pmax_eligibility import (
                            DetectPMaxEligibilityUseCase,
                        )
                        from adcopilot.domain.launch.templates import detect_vertical_from_description
                        from adcopilot.infrastructure.db.models import (
                            GoogleAdsAccountModel,
                            OAuthCredentialsModel,
                        )
                        import uuid as _uuid
                        from sqlalchemy import select as _select

                        _acct_q = await session.execute(
                            _select(GoogleAdsAccountModel).where(
                                GoogleAdsAccountModel.id == _uuid.UUID(str(brief.account_id))
                            )
                        )
                        _acct = _acct_q.scalar_one_or_none()
                        _creds_q = await session.execute(
                            _select(OAuthCredentialsModel).where(
                                OAuthCredentialsModel.account_id == _uuid.UUID(str(brief.account_id))
                            )
                        )
                        _creds = _creds_q.scalar_one_or_none()
                        if _acct and _creds:
                            _vertical = (
                                _acct.vertical
                                or detect_vertical_from_description(brief.business_description or "")
                            )

                            class _FeedProvider:
                                async def query_merchant_center_feed(
                                    self, refresh_token: str, customer_id: str
                                ) -> list:
                                    from adcopilot.infrastructure.google_ads.queries import (
                                        query_merchant_center_feed,
                                    )
                                    return await query_merchant_center_feed(
                                        refresh_token, customer_id, settings
                                    )

                            _pmax_uc = DetectPMaxEligibilityUseCase(feed_provider=_FeedProvider())
                            _pmax_result = await _pmax_uc.run(
                                vertical=_vertical,
                                refresh_token=_creds.refresh_token,
                                customer_id=_acct.customer_id,
                            )
                            if _pmax_result.eligible:
                                feed_name = _pmax_result.feeds[0].get("name") or "your product feed"
                                await query.edit_message_text(
                                    f"🛒 I see you have a product feed ({feed_name}) linked to your account!\n\n"
                                    "Would you like a **Performance Max** campaign? "
                                    "(recommended for e-commerce — uses your product catalog)\n\n"
                                    "Performance Max campaigns automatically show your products across "
                                    "Google Search, Shopping, Display, YouTube and Maps.\n\n"
                                    "⚡ Generating your PMax campaign proposal now…"
                                )
                                generate_brief_id = brief_id_str
                                logger.info(
                                    "PMax campaign generation dispatched",
                                    brief_id=brief_id_str,
                                    feed=feed_name,
                                )
                                updated = dataclasses.replace(brief, status=LaunchStatus.GENERATING)
                                await repo.save(updated)
                                # Skip to the standard generation flow below (same task)
                    except Exception as _pmax_err:
                        logger.debug("PMax eligibility check skipped", error=str(_pmax_err))
                    # --- end PMax check ---

                    if not generate_brief_id:
                        updated = dataclasses.replace(brief, status=LaunchStatus.GENERATING)
                        await repo.save(updated)
                        await query.edit_message_text(
                            "⏳ Generating your campaign proposal…\n\n"
                            "I'll notify you when it's ready! This usually takes 30–60 seconds."
                        )
                        generate_brief_id = brief_id_str
                    logger.info("campaign generation dispatched", brief_id=brief_id_str)

            # ── iv_fix:{brief_id} ─────────────────────────────────────────────
            elif data.startswith("iv_fix:"):
                brief_id_str = data.split(":", 1)[1]
                keyboard = _fix_keyboard(brief_id_str)
                await query.edit_message_text(
                    "Which answer would you like to change?",
                    reply_markup=keyboard,
                )

            # ── iv_fix_q:{brief_id}:{step} ────────────────────────────────────
            elif data.startswith("iv_fix_q:"):
                _, brief_id_str, step_str = data.split(":", 2)
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if brief and brief.user_id == user_id and brief.status == LaunchStatus.COLLECTING:
                    result_ir = await fsm_fix_step(brief, int(step_str), repo)
                    await _send_result(query, result_ir, edit=True)

            # ── iv_voice_ok:{brief_id}:{b64text} ─────────────────────────────
            elif data.startswith("iv_voice_ok:"):
                import base64

                parts = data.split(":", 2)
                brief_id_str, encoded_text = parts[1], parts[2]
                text = base64.urlsafe_b64decode(encoded_text).decode(errors="replace")
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if brief and brief.user_id == user_id and brief.status == LaunchStatus.COLLECTING:
                    try:
                        result_ir = await fsm_handle_text(brief, text, repo)
                        await _send_result(query, result_ir, edit=True)
                    except ValueError as exc:
                        await query.edit_message_text(str(exc))

            # ── iv_voice_no:{brief_id} ────────────────────────────────────────
            elif data.startswith("iv_voice_no:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if brief and brief.user_id == user_id and brief.status == LaunchStatus.COLLECTING:
                    step = brief.interview_step
                    await query.edit_message_text(
                        f"No problem! Please type your answer to:\n\n{QUESTIONS[step]}"
                    )

    except Exception:
        logger.exception("interview_callback_handler error", data=data)
        await query.answer("An error occurred. Please try again.", show_alert=True)
        return
    finally:
        await engine.dispose()

    # Dispatch after DB session committed to avoid race condition
    if generate_brief_id is not None:
        from adcopilot.interfaces.worker.tasks import generate_campaign_task

        generate_campaign_task.delay(
            generate_brief_id, None, telegram_chat_id
        )


async def _send_result(
    query: object,
    result: InterviewResult,
    *,
    edit: bool,
) -> None:
    """Send or edit a Telegram message with the FSM result."""
    from telegram import CallbackQuery

    assert isinstance(query, CallbackQuery)
    if edit:
        await query.edit_message_text(
            result.text,
            reply_markup=result.keyboard,
            parse_mode="Markdown",
        )
    else:
        from telegram import Message

        if isinstance(query.message, Message):
            await query.message.reply_text(
                result.text,
                reply_markup=result.keyboard,
                parse_mode="Markdown",
            )


# ---------------------------------------------------------------------------
# /cancel command handler
# ---------------------------------------------------------------------------


async def cancel_interview_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/cancel — abandon the active interview."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import UserModel

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "You don't have a linked account. Use /start to connect one."
                )
                return

            user_id = UserId(str(user_model.id))
            repo = SqlCampaignBriefRepository(session)
            brief = await repo.get_active_for_user(user_id)

            if brief is None:
                await update.message.reply_text(
                    "No active interview to cancel. You can start one with /launch."
                )
                return

            await fsm_cancel(brief, repo)

    except Exception:
        logger.exception("cancel_interview_handler error")
        await update.message.reply_text("An error occurred. Please try again.")
        return
    finally:
        await engine.dispose()

    await update.message.reply_text(
        "❌ Interview cancelled. "
        "Send /launch whenever you're ready to start a new campaign."
    )


# ---------------------------------------------------------------------------
# /launch command handler (manual trigger)
# ---------------------------------------------------------------------------


async def launch_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """/launch — show 'Start interview' prompt for the user's first account."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.domain.entities import UserId
            from adcopilot.infrastructure.db.models import UserModel
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Please link your Google Ads account first via /start."
                )
                return

            user_id = UserId(str(user_model.id))
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(user_id)

            if not accounts:
                await update.message.reply_text(
                    "No Google Ads accounts connected. Visit the web app to connect one."
                )
                return

            # Check for an existing active interview
            repo = SqlCampaignBriefRepository(session)
            active = await repo.get_active_for_user(user_id)

            if active is not None:
                step = active.interview_step
                # Resume existing interview
                resume_text = (
                    "You have an interview in progress! Let's continue.\n\n"
                    + _resume_banner(active)
                    + "\n\n"
                    + QUESTIONS[step]
                )
                keyboard = (
                    _primary_action_keyboard(active.id) if step == 4 else None
                )
                await update.message.reply_text(
                    resume_text, reply_markup=keyboard, parse_mode="Markdown"
                )
                return

            # Use the first non-manager account
            account = next((a for a in accounts if not a.is_manager), accounts[0])
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🚀 Start interview",
                            callback_data=f"iv_start:{account.id}",
                        )
                    ]
                ]
            )
            await update.message.reply_text(
                "🎯 *Let's build your first campaign!*\n\n"
                "I'll ask you 6 quick questions to understand your business, "
                "and then generate a complete Google Ads campaign for you.\n\n"
                "Tap the button below when you're ready.",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Voice message handler
# ---------------------------------------------------------------------------


async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle voice messages during an active interview.

    Attempts transcription via the configured service; falls back to asking
    the user to type their answer.
    """
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import UserModel

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                return

            user_id = UserId(str(user_model.id))
            repo = SqlCampaignBriefRepository(session)
            brief = await repo.get_active_for_user(user_id)

            if brief is None or brief.interview_step not in range(1, 7):
                return

            # Attempt transcription
            transcript = await _transcribe_voice(update)

            if transcript is None:
                await update.message.reply_text(
                    "🎙️ I received your voice message, but I can't transcribe audio yet.\n\n"
                    f"Please *type* your answer to:\n\n{QUESTIONS[brief.interview_step]}",
                    parse_mode="Markdown",
                )
                return

            keyboard = _voice_confirm_keyboard(brief.id, transcript)
            await update.message.reply_text(
                f"🎙️ I heard:\n\n_{transcript}_\n\nIs that correct?",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
    finally:
        await engine.dispose()


async def _transcribe_voice(update: Update) -> str | None:
    """Attempt to transcribe a voice message.  Returns None if unavailable."""
    # Placeholder: a real implementation would download the file and call
    # a speech-to-text API (e.g. Whisper).  Returning None causes the bot
    # to ask the user to type instead.
    return None


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------


def _resume_banner(brief: CampaignBrief) -> str:
    """Return a concise progress summary for the resume message."""
    lines = ["📌 *Progress so far:*"]
    if brief.business_description:
        lines.append(f"1️⃣ Business: {brief.business_description}")
    if brief.location:
        lines.append(f"2️⃣ Location: {brief.location}")
    if brief.typical_customer_value and brief.typical_customer_value > 0:
        lines.append(f"3️⃣ Customer value: {brief.typical_customer_value:,.0f} PLN")
    if brief.primary_action:
        lines.append(f"4️⃣ Goal: {brief.primary_action}")
    if brief.monthly_budget_pln and brief.monthly_budget_pln > 0:
        lines.append(f"5️⃣ Budget: {brief.monthly_budget_pln:,.0f} PLN/month")
    return "\n".join(lines)


RESUME_THRESHOLD = timedelta(hours=24)


def is_long_pause(brief: CampaignBrief) -> bool:
    """True when the brief has been idle for more than 24 hours."""
    return (datetime.now(UTC) - brief.created_at) >= RESUME_THRESHOLD
