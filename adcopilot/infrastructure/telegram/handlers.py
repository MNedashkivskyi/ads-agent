"""Telegram command handlers."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import redis as redis_sync
import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.config import get_settings
from adcopilot.domain.entities import UserId
from adcopilot.domain.recommendation import RecommendationStatus
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
from adcopilot.interfaces.api.telegram import _verify_link_token

logger = structlog.get_logger(__name__)

_STATUS_EMOJI = {
    RecommendationStatus.PENDING: "⏳",
    RecommendationStatus.APPROVED: "✅",
    RecommendationStatus.DECLINED: "❌",
    RecommendationStatus.EXECUTED: "✅",
    RecommendationStatus.FAILED: "⚠️",
    RecommendationStatus.EXPIRED: "💤",
}


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start [jwt] — link Telegram account or show welcome message."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    args: list[str] = list(context.args or [])

    if not args:
        await update.message.reply_text(
            "Witaj! Jestem AdsWise — Twój asystent Google Ads.\n\n"
            "Aby połączyć konto, odwiedź adswise.xyz/app/telegram i zeskanuj kod QR."
        )
        return

    deep_link_token = args[0]
    settings = get_settings()

    redis_client = redis_sync.Redis.from_url(settings.REDIS_URL)
    try:
        user_id = _verify_link_token(deep_link_token, redis_client)
    finally:
        redis_client.close()

    if user_id is None:
        await update.message.reply_text(
            "Ten link wygasł. Wygeneruj nowy na adswise.xyz/app/telegram"
        )
        return

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                await update.message.reply_text(
                    "Użytkownik nie znaleziony. Zarejestruj się na adswise.xyz"
                )
                return

            if user.telegram_chat_id is not None and user.telegram_chat_id == chat_id:
                await update.message.reply_text(
                    f"Jesteś już połączony! Konto {user.email} jest aktywne.\n\n"
                    "Wyślij /help, aby zobaczyć dostępne komendy."
                )
                return

            updated = dataclasses.replace(user, telegram_chat_id=chat_id)
            await repo.save(updated)
            await session.commit()
    finally:
        await engine.dispose()

    await update.message.reply_text(
        f"✅ Konto połączone pomyślnie! Witaj, {user.email}.\n\n"
        "Wyślij /help, aby zobaczyć dostępne komendy."
    )
    logger.info("telegram linked", user_id=user_id, chat_id=chat_id)


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — account summary with last check time and total savings."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import (
                RecommendationModel,
                SnapshotRunModel,
                UserModel,
            )
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Nie masz połączonego konta. Użyj /start z linkiem aktywacyjnym."
                )
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(str(user_model.id)))

            if not accounts:
                await update.message.reply_text(
                    "Brak połączonych kont Google Ads. Odwiedź adswise.xyz, aby połączyć konto."
                )
                return

            lines: list[str] = []
            has_enabled_campaigns = False

            for account in accounts:
                acct_uuid = uuid.UUID(account.id)

                run_result = await session.execute(
                    select(SnapshotRunModel)
                    .where(SnapshotRunModel.account_id == acct_uuid)
                    .order_by(SnapshotRunModel.created_at.desc())
                    .limit(1)
                )
                latest_run = run_result.scalar_one_or_none()
                last_check = (
                    latest_run.created_at.strftime("%Y-%m-%d %H:%M UTC")
                    if latest_run
                    else "brak danych"
                )

                savings_result = await session.execute(
                    select(sa.func.sum(RecommendationModel.estimated_monthly_savings_micros)).where(
                        RecommendationModel.account_id == acct_uuid,
                        RecommendationModel.status == RecommendationStatus.EXECUTED.value,
                    )
                )
                total_savings_micros: int = savings_result.scalar_one() or 0
                total_savings = format_micros_as_currency(total_savings_micros)

                # Check whether this account has any enabled campaigns
                from adcopilot.infrastructure.db.models import CampaignSnapshotModel

                campaign_result = await session.execute(
                    select(CampaignSnapshotModel)
                    .where(
                        CampaignSnapshotModel.account_id == acct_uuid,
                        CampaignSnapshotModel.status == "ENABLED",
                    )
                    .limit(1)
                )
                if campaign_result.scalar_one_or_none() is not None:
                    has_enabled_campaigns = True

                name = account.descriptive_name or account.customer_id
                lines.append(
                    f"📊 *Konto: {name}*\n"
                    f"Ostatnie sprawdzenie: {last_check}\n"
                    f"Oszczędności od początku: {total_savings}"
                )

            # If no enabled campaigns exist across all accounts, offer to build one
            launch_keyboard = None
            if not has_enabled_campaigns and accounts:
                first_account = next(
                    (a for a in accounts if not a.is_manager), accounts[0]
                )
                launch_keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🚀 Let's build your first campaign",
                                callback_data=f"iv_start:{first_account.id}",
                            )
                        ]
                    ]
                )
                lines.append(
                    "\n🎯 *No active campaigns found.*\n"
                    "Tap the button below to create your first campaign!"
                )

            await update.message.reply_text(
                "\n\n".join(lines),
                parse_mode="Markdown",
                reply_markup=launch_keyboard,
            )
    finally:
        await engine.dispose()


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/history — last 10 recommendations across all accounts."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.infrastructure.db.models import RecommendationModel, UserModel
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Nie masz połączonego konta. Użyj /start z linkiem aktywacyjnym."
                )
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(str(user_model.id)))
            if not accounts:
                await update.message.reply_text("Brak połączonych kont Google Ads.")
                return

            account_uuids = [uuid.UUID(a.id) for a in accounts]
            recs_result = await session.execute(
                select(RecommendationModel)
                .where(RecommendationModel.account_id.in_(account_uuids))
                .order_by(RecommendationModel.created_at.desc())
                .limit(10)
            )
            recs = recs_result.scalars().all()

            if not recs:
                await update.message.reply_text("Brak historii rekomendacji.")
                return

            lines: list[str] = []
            for rec in recs:
                status = RecommendationStatus(rec.status)
                emoji = _STATUS_EMOJI.get(status, "❓")
                kind_label = rec.kind.replace("_", " ").title()
                savings = format_micros_as_currency(rec.estimated_monthly_savings_micros)
                date_str = rec.created_at.strftime("%Y-%m-%d")
                lines.append(f"{emoji} {kind_label} — {savings}/mies. ({date_str})")

            await update.message.reply_text(
                "*Ostatnie rekomendacje:*\n" + "\n".join(lines),
                parse_mode="Markdown",
            )
    finally:
        await engine.dispose()


async def pause_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pause — pause daily digest notifications."""
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
                await update.message.reply_text(
                    "Nie masz połączonego konta. Użyj /start z linkiem aktywacyjnym."
                )
                return

            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(str(user_model.id)))
            if user is None:
                await update.message.reply_text("Użytkownik nie znaleziony.")
                return

            updated = dataclasses.replace(user, notifications_paused=True)
            await repo.save(updated)
            await session.commit()
    finally:
        await engine.dispose()

    await update.message.reply_text(
        "⏸ Zatrzymano. Nie będziesz otrzymywać codziennych rekomendacji "
        "do momentu wysłania /resume."
    )


async def resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/resume — resume daily digest notifications."""
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
                await update.message.reply_text(
                    "Nie masz połączonego konta. Użyj /start z linkiem aktywacyjnym."
                )
                return

            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(str(user_model.id)))
            if user is None:
                await update.message.reply_text("Użytkownik nie znaleziony.")
                return

            updated = dataclasses.replace(user, notifications_paused=False)
            await repo.save(updated)
            await session.commit()
    finally:
        await engine.dispose()

    await update.message.reply_text(
        "▶️ Wznowiono. Zaczniesz otrzymywać rekomendacje od jutra rano."
    )


async def undo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/undo — list last executed recommendations with Undo buttons (7-day window)."""
    if update.message is None:
        return

    chat_id = update.message.chat_id
    settings = get_settings()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            from adcopilot.domain.entities import AccountId
            from adcopilot.infrastructure.db.models import UserModel
            from adcopilot.infrastructure.db.repositories.audit_log_repository import (
                SqlAuditLogRepository,
            )
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Nie masz połączonego konta. Użyj /start z linkiem aktywacyjnym."
                )
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            audit_repo = SqlAuditLogRepository(session)

            accounts = await account_repo.list_for_user(UserId(str(user_model.id)))
            account_ids = [AccountId(a.id) for a in accounts]

            since = datetime.now(UTC) - timedelta(days=7)
            recent = await audit_repo.list_recent_executes(account_ids, since)

            if not recent:
                await update.message.reply_text(
                    "Brak akcji do cofnięcia w ostatnich 7 dniach."
                )
                return

            seen: set[str] = set()
            unique = []
            for log in recent:
                if log.recommendation_id not in seen:
                    seen.add(log.recommendation_id)
                    unique.append(log)
                    if len(unique) == 5:
                        break

            await update.message.reply_text(
                f"Ostatnie {len(unique)} wykonanych akcji — kliknij ↩️ Cofnij, aby cofnąć:"
            )
            for log in unique:
                kind_label = log.kind.replace("_", " ").title()
                ts = log.created_at.strftime("%Y-%m-%d %H:%M UTC")
                text = f"{kind_label} — wykonano {ts}"
                keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "↩️ Cofnij",
                                callback_data=f"undo_exec:{log.recommendation_id}",
                            )
                        ]
                    ]
                )
                await update.message.reply_text(text, reply_markup=keyboard)
    finally:
        await engine.dispose()


async def connect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/connect — send a Google Ads OAuth link to the user."""
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
                await update.message.reply_text(
                    "Najpierw połącz konto Telegram przez stronę.\n"
                    "Odwiedź adswise.xyz/app/telegram i zeskanuj kod QR."
                )
                return

            if not settings.GOOGLE_ADS_CLIENT_ID:
                await update.message.reply_text(
                    "Integracja Google Ads nie jest jeszcze skonfigurowana."
                )
                return

            from urllib.parse import urlencode

            from adcopilot.security import issue_state_jwt

            state = issue_state_jwt(str(user_model.id), settings.SECRET_KEY)
            params = {
                "client_id": settings.GOOGLE_ADS_CLIENT_ID,
                "redirect_uri": settings.OAUTH_REDIRECT_URI,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/adwords",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔗 Połącz Google Ads", url=auth_url)]]
            )
            await update.message.reply_text(
                "Kliknij poniższy przycisk, aby połączyć swoje konto Google Ads.\n\n"
                "⚠️ Upewnij się, że jesteś zalogowany na właściwe konto Google.",
                reply_markup=keyboard,
            )
    finally:
        await engine.dispose()


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — list all available commands."""
    if update.message is None:
        return

    text = (
        "*Dostępne komendy:*\n\n"
        "/connect — Połącz konto Google Ads\n"
        "/status — Podsumowanie konta\n"
        "/launch — Utwórz nową kampanię\n"
        "/history — Ostatnie rekomendacje\n"
        "/pause — Wstrzymaj codzienne powiadomienia\n"
        "/resume — Wznów powiadomienia\n"
        "/undo — Cofnij ostatnią zmianę\n"
        "/panic — Natychmiast wstrzymaj wszystkie kampanie\n"
        "/help — Lista komend"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all: routes to the active interview if one exists, else shows help."""
    if update.message is None or update.message.text is None:
        return

    chat_id = update.message.chat_id
    text = update.message.text

    # /skip is only meaningful during Q6 of the interview
    is_skip = text.strip().lower() in ("/skip", "skip")

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    revision_brief_id: str | None = None
    revision_text: str | None = None
    try:
        async with AsyncSession(engine) as session, session.begin():
            from sqlalchemy import select

            from adcopilot.domain.entities import UserId
            from adcopilot.infrastructure.db.models import UserModel
            from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
                SqlCampaignBriefRepository,
            )
            from adcopilot.infrastructure.telegram.interview_handler import (
                QUESTIONS,
                _primary_action_keyboard,
                _resume_banner,
                fsm_handle_text,
                fsm_skip_q6,
                is_long_pause,
            )

            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id == chat_id)
            )
            user_model = result.scalar_one_or_none()
            if user_model is None:
                await update.message.reply_text(
                    "Mogę pomóc z Twoim kontem Google Ads. Wyślij /help, aby zobaczyć dostępne komendy."
                )
                return

            user_id = UserId(str(user_model.id))
            repo = SqlCampaignBriefRepository(session)
            brief = await repo.get_active_for_user(user_id)

            if brief is None or brief.interview_step == 0:
                await update.message.reply_text(
                    "Mogę pomóc z Twoim kontem Google Ads. Wyślij /help, aby zobaczyć dostępne komendy."
                )
                return

            step = brief.interview_step

            # ── Step 8: revision mode (user submitted change request) ─────────
            if step == 8:
                import dataclasses as _dc

                from adcopilot.domain.launch.entities import LaunchStatus

                # Transition back to GENERATING immediately so no duplicate requests
                updated = _dc.replace(
                    brief,
                    status=LaunchStatus.GENERATING,
                    interview_step=7,
                )
                await repo.save(updated)
                await update.message.reply_text(
                    "⏳ Revising your proposal based on your feedback…\n\n"
                    "I'll notify you when the updated proposal is ready."
                )
                revision_brief_id = str(brief.id)
                revision_text = text
                return  # fall through to task dispatch below

            # Resume banner after long pause
            if is_long_pause(brief):
                banner = (
                    "👋 Welcome back! Let's continue your campaign interview.\n\n"
                    + _resume_banner(brief)
                    + "\n\n"
                )
            else:
                banner = ""

            # Q4 is answered via inline buttons only
            if step == 4:
                keyboard = _primary_action_keyboard(brief.id)
                await update.message.reply_text(
                    banner + QUESTIONS[4],
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                return

            # /skip shortcut for Q6
            if step == 6 and is_skip:
                ir = await fsm_skip_q6(brief, repo)
            else:
                try:
                    ir = await fsm_handle_text(brief, text, repo)
                except ValueError as exc:
                    await update.message.reply_text(f"⚠️ {exc}")
                    return

            reply = banner + ir.text if banner else ir.text
            await update.message.reply_text(
                reply, reply_markup=ir.keyboard, parse_mode="Markdown"
            )
    finally:
        await engine.dispose()

    # Dispatch revision task after DB session commits
    if revision_brief_id is not None:
        from adcopilot.interfaces.worker.tasks import generate_campaign_task

        generate_campaign_task.delay(revision_brief_id, revision_text, chat_id)
