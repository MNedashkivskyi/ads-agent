"""Seed synthetic Quality Score data for a test account.

Why this exists
---------------
Quality Score values come from Google Ads and only land in our database
after a nightly snapshot of a real, spending account. You cannot push QS
back into Google, so a fresh demo account shows only empty states. This
script writes the same rows the snapshot pipeline would, directly into
Postgres, so the Quality Score page (``/app/quality-score``) can be
exercised end-to-end against real data:

* ``keyword_snapshots``   -> powers "Bieżące wyniki" (the table + averages)
                             and makes low-QS keywords eligible for a plan
                             ("Utwórz plan" needs QS <= 5 and >= 100 impressions).
* ``keyword_qs_history``  -> powers "Trendy QS" (per-keyword trend charts);
                             needs several days of rows to draw a line.

It is idempotent: re-running upserts on the same unique keys
(``uq_keyword_snapshots`` / ``uq_keyword_qs_history_account_criterion_date``).

Usage
-----
    # by internal account id (UUID):
    uv run python scripts/seed_quality_score_data.py --account-id <uuid>

    # or resolve the user's primary account (same accounts[0] the API uses):
    uv run python scripts/seed_quality_score_data.py --user-id <supabase-user-id>

    # tune trend length / wipe previously-seeded rows first:
    uv run python scripts/seed_quality_score_data.py --account-id <uuid> --days 21 --clear

DATABASE_URL is read from the environment (or .env). Point it at the target
database — e.g. the Railway dev Postgres — before running.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

# Make sure the project root is importable regardless of cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    """Load .env into os.environ (values already present are NOT overwritten)."""
    import os

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# A fixed synthetic ad group so plans get a stable target_ad_group_resource_name.
_AD_GROUP_ID = 1_111_111_111

# (text, match_type, quality_score, expected_ctr, ad_relevance, landing_page, impressions, clicks)
# A spread of low/medium/high QS so the table is varied AND a few keywords are
# plan-eligible (QS <= 5 and impressions >= 100).
_KEYWORDS: list[tuple[str, str, int, str, str, str, int, int]] = [
    ("buty zimowe damskie", "EXACT", 3, "BELOW_AVERAGE", "AVERAGE", "BELOW_AVERAGE", 5400, 92),
    ("kurtki puchowe meskie", "PHRASE", 4, "BELOW_AVERAGE", "BELOW_AVERAGE", "AVERAGE", 3120, 70),
    ("tanie sniegowce", "BROAD", 5, "AVERAGE", "BELOW_AVERAGE", "AVERAGE", 2080, 61),
    ("czapki zimowe", "PHRASE", 6, "AVERAGE", "AVERAGE", "AVERAGE", 1450, 55),
    ("rekawiczki narciarskie", "EXACT", 7, "ABOVE_AVERAGE", "AVERAGE", "AVERAGE", 980, 44),
    ("kombinezon narciarski", "PHRASE", 9, "ABOVE_AVERAGE", "ABOVE_AVERAGE", "ABOVE_AVERAGE", 760, 51),
]


def _criterion_id(index: int) -> int:
    """Stable synthetic criterion id per keyword index."""
    return 2_000_000_000 + index


async def _resolve_account_id(session, args) -> str:
    if args.account_id:
        return args.account_id
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    repo = SqlGoogleAdsAccountRepository(session)
    accounts = await repo.list_for_user(args.user_id)
    if not accounts:
        raise SystemExit(f"No Google Ads accounts found for user {args.user_id}")
    primary = accounts[0]
    print(f"Resolved primary account {primary.id} (customer_id={primary.customer_id})")
    return str(primary.id)


async def _clear(session, account_uuid: uuid.UUID) -> None:
    from sqlalchemy import delete

    from adcopilot.infrastructure.db.models import (
        KeywordQSHistoryModel,
        KeywordSnapshotModel,
    )

    crit_ids = [_criterion_id(i) for i in range(len(_KEYWORDS))]
    for model in (KeywordSnapshotModel, KeywordQSHistoryModel):
        await session.execute(
            delete(model).where(
                model.account_id == account_uuid,
                model.criterion_id.in_(crit_ids),
            )
        )
    print("Cleared previously-seeded rows for these synthetic keywords.")


async def _seed(session, account_uuid: uuid.UUID, days: int) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from adcopilot.infrastructure.db.models import (
        KeywordQSHistoryModel,
        KeywordSnapshotModel,
    )

    today = date.today()

    # --- keyword_snapshots: a single latest snapshot (today) per keyword -----
    snapshot_rows = []
    for i, (text, match_type, qs, ectr, adrel, lpx, impr, clicks) in enumerate(_KEYWORDS):
        snapshot_rows.append(
            {
                "id": uuid.uuid4(),
                "account_id": account_uuid,
                "snapshot_date": today,
                "criterion_id": _criterion_id(i),
                "ad_group_id": _AD_GROUP_ID,
                "text": text,
                "match_type": match_type,
                "status": "ENABLED",
                "quality_score": qs,
                "expected_ctr": ectr,
                "ad_relevance": adrel,
                "landing_page_experience": lpx,
                "impressions": impr,
                "clicks": clicks,
                "cost_micros": clicks * 1_200_000,
                "conversions": round(clicks * 0.06, 2),
                "ctr": round(clicks / impr, 4) if impr else 0.0,
                "avg_cpc_micros": 1_200_000,
            }
        )
    stmt = pg_insert(KeywordSnapshotModel).values(snapshot_rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_keyword_snapshots",
        set_={
            "quality_score": stmt.excluded.quality_score,
            "expected_ctr": stmt.excluded.expected_ctr,
            "ad_relevance": stmt.excluded.ad_relevance,
            "landing_page_experience": stmt.excluded.landing_page_experience,
            "impressions": stmt.excluded.impressions,
            "clicks": stmt.excluded.clicks,
            "ctr": stmt.excluded.ctr,
        },
    )
    await session.execute(stmt)
    print(f"Upserted {len(snapshot_rows)} keyword_snapshots rows (snapshot_date={today}).")

    # --- keyword_qs_history: `days` daily points per keyword ----------------
    history_rows = []
    for i, (text, match_type, qs, ectr, adrel, lpx, _impr, _clicks) in enumerate(_KEYWORDS):
        for d in range(days):
            recorded = today - timedelta(days=days - 1 - d)
            # Gentle upward drift toward the current QS so the chart shows a trend.
            drift = max(1, qs - (days - 1 - d) // 5)
            history_rows.append(
                {
                    "id": uuid.uuid4(),
                    "account_id": account_uuid,
                    "criterion_id": _criterion_id(i),
                    "recorded_date": recorded,
                    "keyword_text": text,
                    "match_type": match_type,
                    "quality_score": min(drift, qs),
                    "expected_ctr": ectr,
                    "ad_relevance": adrel,
                    "landing_page_experience": lpx,
                }
            )
    stmt = pg_insert(KeywordQSHistoryModel).values(history_rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_keyword_qs_history_account_criterion_date",
        set_={
            "quality_score": stmt.excluded.quality_score,
            "expected_ctr": stmt.excluded.expected_ctr,
            "ad_relevance": stmt.excluded.ad_relevance,
            "landing_page_experience": stmt.excluded.landing_page_experience,
        },
    )
    await session.execute(stmt)
    print(f"Upserted {len(history_rows)} keyword_qs_history rows ({days} days x {len(_KEYWORDS)} kw).")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account-id", help="Internal Google Ads account UUID to seed.")
    group.add_argument("--user-id", help="Supabase user id; seeds their primary account.")
    parser.add_argument("--days", type=int, default=14, help="Trend history length (default 14).")
    parser.add_argument(
        "--clear", action="store_true", help="Delete previously-seeded synthetic rows first."
    )
    args = parser.parse_args()

    _load_env()

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    settings = get_settings()
    # Railway/Heroku hand out a plain ``postgresql://`` URL, which SQLAlchemy
    # maps to the (sync) psycopg2 driver. This script uses an async engine, so
    # normalize the scheme to asyncpg if no async driver was specified.
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url)
    try:
        async with AsyncSession(engine) as session:
            account_id = await _resolve_account_id(session, args)
            account_uuid = uuid.UUID(account_id)
            if args.clear:
                await _clear(session, account_uuid)
            await _seed(session, account_uuid, args.days)
            await session.commit()
    finally:
        await engine.dispose()

    print("\nDone. Open /app/quality-score for this account to see populated data.")


if __name__ == "__main__":
    asyncio.run(main())
