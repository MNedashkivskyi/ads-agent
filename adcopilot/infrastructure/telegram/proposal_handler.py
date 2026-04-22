"""Telegram handlers for the campaign proposal review and launch flow.

After GenerateCampaignProposalUseCase completes, the user receives a
proposal summary message with four inline buttons:

  Row 1: [📄 See full details]  [✅ Launch this campaign]
  Row 2: [✏️ Make changes]      [❌ Start over]

Button behaviours
-----------------
See full details  → opens /app/launch/preview/<proposal_id> in browser (URL button)
Launch            → dispatches create_campaign_task; sends "Campaigns created and paused"
                    message with [🚀 Enable and go live] [🔙 Don't enable yet]
Enable and go live→ dispatches enable_campaign_task; sends live confirmation + schedules monitoring
Make changes      → sets brief to step=8 (revision mode); awaits free text from user
Start over        → marks brief ABANDONED; invites user to /launch again
Pause everything  → dispatches panic_pause_campaigns_task for the account

/panic command pauses all enabled campaigns across all user accounts within 30 seconds.
"""

from __future__ import annotations

import dataclasses

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adcopilot.config import get_settings
from adcopilot.domain.entities import UserId
from adcopilot.domain.launch.entities import CampaignBriefId, CampaignProposal, LaunchStatus

logger = structlog.get_logger(__name__)

_MICROS_PER_PLN = 1_000_000


# ---------------------------------------------------------------------------
# Summary formatter
# ---------------------------------------------------------------------------


def format_proposal_summary(proposal: CampaignProposal) -> str:
    """Format a ≤15-line proposal summary suitable for a Telegram message."""
    from adcopilot.domain.polish_market.currency import format_pln_micros, format_pln
    total_kws = sum(len(ag.keywords) for ag in proposal.ad_groups)
    total_ads = sum(len(ag.ads) for ag in proposal.ad_groups)
    cpc_min_pln = proposal.estimated_cpc_range[0] / _MICROS_PER_PLN
    cpc_max_pln = proposal.estimated_cpc_range[1] / _MICROS_PER_PLN

    lines = [
        f"🎯 *Campaign Proposal: {proposal.campaign_name}*",
        "",
        f"💰 Dzienny budżet: {format_pln_micros(proposal.daily_budget_micros)}",
        f"📍 Targeting: {proposal.location_targeting}",
        f"📈 Bidding: {proposal.bidding_strategy}",
        f"📊 Structure: {len(proposal.ad_groups)} ad groups · {total_kws} keywords · {total_ads} ads",
        f"🚫 Negative keywords: {len(proposal.negative_keywords)}",
        f"💵 Est. CPC: {format_pln(cpc_min_pln)}–{format_pln(cpc_max_pln)}",
    ]

    if proposal.compliance_warnings:
        lines.append("")
        lines.append("⚠️ *Uwagi dotyczące zgodności reklamy:*")
        for w in proposal.compliance_warnings:
            severity = w.get("severity", "")
            message = w.get("message", "")
            suggestion = w.get("suggestion", "")
            line = f"- [{severity}] {message}"
            if suggestion:
                line += f". Sugestia: _{suggestion}_"
            lines.append(line)

    if proposal.seasonal_multiplier != 1.0:
        if proposal.seasonal_multiplier > 1.0:
            lines.append(
                f"📅 Sezon szczytowy dla tej branży (mnożnik {proposal.seasonal_multiplier:.2f}×) — "
                "budżet może wyczerpać się szybciej niż zwykle."
            )
        else:
            lines.append(
                f"📅 Niski sezon dla tej branży (mnożnik {proposal.seasonal_multiplier:.2f}×) — "
                "możesz uzyskać lepszą wartość za budżet."
            )

    if proposal.brand_campaign_name:
        brand_budget_formatted = format_pln_micros(proposal.brand_daily_budget_micros)
        lines += [
            "",
            f"🏷️ *Brand campaign: {proposal.brand_campaign_name}*",
            f"   Budget: {brand_budget_formatted}/dzień · {len(proposal.brand_keywords)} brand keywords · MAXIMIZE_CLICKS",
        ]

    # Example ad from the first ad group
    if proposal.ad_groups and proposal.ad_groups[0].ads:
        example_ad = proposal.ad_groups[0].ads[0]
        headline = example_ad.headlines[0] if example_ad.headlines else ""
        description = example_ad.descriptions[0] if example_ad.descriptions else ""
        lines += [
            "",
            "📝 *Example ad:*",
            f"_{headline}_",
            f"_{description}_",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def proposal_action_keyboard(
    proposal_id: str,
    brief_id: str,
    app_url: str | None,
) -> InlineKeyboardMarkup:
    """Four-button keyboard shown with the proposal summary."""
    row1: list[InlineKeyboardButton] = []

    if app_url:
        preview_url = f"{app_url.rstrip('/')}/app/launch/preview/{proposal_id}"
        row1.append(InlineKeyboardButton("📄 See full details", url=preview_url))

    row1.append(
        InlineKeyboardButton(
            "✅ Launch this campaign",
            callback_data=f"proposal_launch:{brief_id}",
        )
    )

    row2 = [
        InlineKeyboardButton(
            "✏️ Make changes",
            callback_data=f"proposal_changes:{brief_id}",
        ),
        InlineKeyboardButton(
            "❌ Start over",
            callback_data=f"proposal_restart:{brief_id}",
        ),
    ]

    return InlineKeyboardMarkup([row1, row2])


def post_launch_keyboard(brief_id: str) -> InlineKeyboardMarkup:
    """Two-button keyboard shown after campaign creation (PAUSED)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🚀 Enable and go live",
                    callback_data=f"proposal_enable:{brief_id}",
                ),
                InlineKeyboardButton(
                    "🔙 Don't enable yet",
                    callback_data=f"proposal_keep_paused:{brief_id}",
                ),
            ]
        ]
    )


def panic_pause_keyboard(account_id: str) -> InlineKeyboardMarkup:
    """Single panic button for monitoring alerts."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛑 Pause everything now",
                    callback_data=f"campaign_panic_pause:{account_id}",
                )
            ]
        ]
    )


# ---------------------------------------------------------------------------
# Callback router
# ---------------------------------------------------------------------------


async def proposal_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all proposal_* and campaign_panic_pause callback_data strings."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    await query.answer()

    data = query.data
    telegram_chat_id = query.from_user.id if query.from_user else None
    if telegram_chat_id is None:
        return

    settings = get_settings()
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    task_to_dispatch: tuple[str, str] | None = None  # (task_name, brief_id_or_account_id)
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == telegram_chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await query.answer("Please link your account first with /start.", show_alert=True)
                return

            user_id = UserId(str(user_model.id))
            repo = SqlCampaignBriefRepository(session)

            # ── proposal_launch:{brief_id} ────────────────────────────────
            if data.startswith("proposal_launch:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if not brief or brief.user_id != user_id:
                    return
                if brief.status != LaunchStatus.PROPOSED:
                    await query.answer("This proposal is no longer active.", show_alert=True)
                    return
                updated = dataclasses.replace(brief, status=LaunchStatus.APPROVED)
                await repo.save(updated)
                await query.edit_message_text(
                    "⏳ Creating your campaign in Google Ads...\n\n"
                    "I'll notify you when it's ready (usually under 30 seconds)."
                )
                task_to_dispatch = ("create_campaign", brief_id_str)

            # ── proposal_changes:{brief_id} ───────────────────────────────
            elif data.startswith("proposal_changes:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if not brief or brief.user_id != user_id:
                    return
                if brief.status != LaunchStatus.PROPOSED:
                    await query.answer("This proposal is no longer active.", show_alert=True)
                    return
                # Enter revision mode: status → COLLECTING, step=8
                updated = dataclasses.replace(
                    brief,
                    status=LaunchStatus.COLLECTING,
                    interview_step=8,
                )
                await repo.save(updated)
                await query.edit_message_text(
                    "✏️ What would you like to change?\n\n"
                    "Describe the changes you want and I'll revise the proposal for you."
                )

            # ── proposal_restart:{brief_id} ───────────────────────────────
            elif data.startswith("proposal_restart:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if not brief or brief.user_id != user_id:
                    return
                updated = dataclasses.replace(brief, status=LaunchStatus.ABANDONED)
                await repo.save(updated)
                await query.edit_message_text(
                    "❌ Proposal abandoned.\n\n"
                    "Send /launch whenever you're ready to start a new campaign."
                )

            # ── proposal_enable:{brief_id} ────────────────────────────────
            elif data.startswith("proposal_enable:"):
                brief_id_str = data.split(":", 1)[1]
                brief = await repo.get(CampaignBriefId(brief_id_str))
                if not brief or brief.user_id != user_id:
                    return
                if brief.status != LaunchStatus.CREATED_PAUSED:
                    await query.answer("Campaign is not in PAUSED state.", show_alert=True)
                    return
                if not brief.campaign_resource_name:
                    await query.answer(
                        "Campaign resource name missing — please contact support.",
                        show_alert=True,
                    )
                    return
                await query.edit_message_text(
                    "⏳ Enabling your campaign...\n\nYou'll get a confirmation shortly."
                )
                task_to_dispatch = ("enable_campaign", brief_id_str)

            # ── proposal_keep_paused:{brief_id} ──────────────────────────
            elif data.startswith("proposal_keep_paused:"):
                brief_id_str = data.split(":", 1)[1]
                await query.edit_message_text(
                    "✅ Campaign remains paused.\n\n"
                    "You can enable it any time by returning to this chat or visiting the web app.\n"
                    "Send /launch to review your campaign status."
                )

            # ── campaign_panic_pause:{account_id} ────────────────────────
            elif data.startswith("campaign_panic_pause:"):
                account_id_str = data.split(":", 1)[1]
                await query.edit_message_text(
                    "🛑 Pausing all campaigns immediately...\n\n"
                    "I'll confirm once all campaigns are paused."
                )
                task_to_dispatch = ("panic_pause", account_id_str)

    except Exception:
        logger.exception("proposal_callback_handler error", data=data)
        await query.answer("An error occurred. Please try again.", show_alert=True)
        return
    finally:
        await engine.dispose()

    # Dispatch Celery tasks AFTER the DB session commits
    if task_to_dispatch:
        from adcopilot.interfaces.worker.tasks import (
            create_campaign_task,
            enable_campaign_task,
            panic_pause_campaigns_task,
        )

        task_name, arg = task_to_dispatch
        if task_name == "create_campaign":
            create_campaign_task.delay(arg, telegram_chat_id)
        elif task_name == "enable_campaign":
            enable_campaign_task.delay(arg, telegram_chat_id)
        elif task_name == "panic_pause":
            panic_pause_campaigns_task.delay(arg, telegram_chat_id)


# ---------------------------------------------------------------------------
# /panic command handler
# ---------------------------------------------------------------------------


async def panic_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/panic — pause all enabled campaigns across all accounts immediately."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    account_ids: list[str] = []
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "You don't have a linked account. Use /start to connect one."
                )
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(str(user_model.id)))
            account_ids = [str(a.id) for a in accounts if not a.is_manager]
    finally:
        await engine.dispose()

    if not account_ids:
        await update.message.reply_text("No Google Ads accounts connected. Nothing to pause.")
        return

    await update.message.reply_text(
        f"🛑 *PANIC: Pausing all campaigns across {len(account_ids)} account(s)...*\n\n"
        "I'll send you a confirmation once all campaigns are paused.",
        parse_mode="Markdown",
    )

    from adcopilot.interfaces.worker.tasks import panic_pause_campaigns_task

    for account_id in account_ids:
        panic_pause_campaigns_task.delay(account_id, chat_id)

    logger.info("panic triggered", chat_id=chat_id, accounts=len(account_ids))
