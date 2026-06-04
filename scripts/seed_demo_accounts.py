"""Seed scenario-rich synthetic demo businesses (CLI wrapper).

The real logic lives in ``adcopilot.infrastructure.demo.seeder`` so it can be
shared with the admin HTTP endpoint (``POST /api/admin/demo/seed``) — handy on
Railway, where this CLI can't be run directly.

Each demo account is a distinct Polish-market business (its own vertical) with
~8 weeks of daily snapshots and one deliberately-planted scenario so a specific
detection rule has something to fire on. Each account also carries account-level
negatives, campaign extensions (with deliberate gaps), device / geo / hour /
day-of-week performance breakdowns, one PENDING recommendation matching its
planted scenario, and weekly digest + insight notifications.

Owner model (Approach A): pass ``--owner-email`` (or ``--owner-user-id``) to
attach all demo accounts to an EXISTING user (e.g. your admin), so one login can
manage them all separately via the account switcher. Without it, self-contained
``demo{i}@demo.local`` users are created instead.

Demo data is identified for cleanup by the ``[DEMO]`` account-name prefix;
``--reset`` wipes prior demo rows first (owner-safe — never deletes the admin).

Usage
-----
    # validate generation logic WITHOUT a database (no Postgres needed):
    python scripts/seed_demo_accounts.py --dry-run

    # seed against the configured DATABASE_URL, owned by your admin user:
    python scripts/seed_demo_accounts.py --reset --owner-email admin@adswise.demo

    # tune:
    python scripts/seed_demo_accounts.py --reset --days 56 --end-date 2026-06-04

Refuses to run when ENV=production unless --force is given.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adcopilot.infrastructure.demo.seeder import (  # noqa: E402
    DEMO_BUSINESSES,
    build_demo_rows,
    count_rows,
    resolve_owner_user_id,
    seed_demo_data,
)


async def _persist(
    *, businesses: list[dict], days: int, end_date: date, reset: bool, owner_email: str | None,
    owner_user_id: uuid.UUID | None,
) -> dict[str, int]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    engine = create_async_engine(get_settings().DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            resolved = owner_user_id
            if resolved is None and owner_email:
                resolved = await resolve_owner_user_id(session, owner_email=owner_email)
                if resolved is None:
                    raise SystemExit(f"ERROR: no user found with email {owner_email!r}")
            return await seed_demo_data(
                session,
                businesses=businesses,
                days=days,
                end_date=end_date,
                reset=reset,
                owner_user_id=resolved,
            )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed scenario-rich demo accounts.")
    parser.add_argument("--accounts", type=int, default=len(DEMO_BUSINESSES))
    parser.add_argument("--days", type=int, default=56)
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD; defaults to today")
    parser.add_argument("--reset", action="store_true", help="wipe prior demo data first")
    parser.add_argument("--dry-run", action="store_true", help="build rows in memory, no DB")
    parser.add_argument("--force", action="store_true", help="allow running when ENV=production")
    parser.add_argument(
        "--owner-email", type=str, default=None,
        help="attach all demo accounts to this EXISTING user's email (Approach A)",
    )
    parser.add_argument(
        "--owner-user-id", type=str, default=None,
        help="attach all demo accounts to this EXISTING user UUID (alternative to --owner-email)",
    )
    args = parser.parse_args()

    end_date = date.fromisoformat(args.end_date) if args.end_date else datetime.now(tz=UTC).date()
    businesses = DEMO_BUSINESSES[: args.accounts]
    owner_user_id = uuid.UUID(args.owner_user_id) if args.owner_user_id else None

    # Dry-run: build in memory only (owner resolution needs a DB, so skip it here).
    if args.dry_run:
        counts = count_rows(
            build_demo_rows(businesses, days=args.days, end_date=end_date, owner_user_id=owner_user_id)
        )
        _print_counts(businesses, counts, days=args.days, end_date=end_date)
        print("\n[dry-run] nothing written.")
        return 0

    from adcopilot.config import get_settings

    settings = get_settings()
    if getattr(settings, "ENV", "") == "production" and not args.force:
        print("\nERROR: ENV=production. Refusing to seed demo data. Use --force to override.")
        return 2

    counts = asyncio.run(
        _persist(
            businesses=businesses,
            days=args.days,
            end_date=end_date,
            reset=args.reset,
            owner_email=args.owner_email,
            owner_user_id=owner_user_id,
        )
    )
    _print_counts(businesses, counts, days=args.days, end_date=end_date)
    target = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "DB"
    owner = args.owner_email or args.owner_user_id or "(self-contained demo users)"
    print(f"\nSeeded into {target}. Owner: {owner}.")
    return 0


def _print_counts(businesses: list[dict], counts: dict[str, int], *, days: int, end_date: date) -> None:
    print(f"Built {len(businesses)} demo businesses, {days} days ending {end_date}:")
    for key, n in sorted(counts.items()):
        print(f"  {key:20s} {n:>7,} rows")
    print(f"  {'TOTAL':20s} {sum(counts.values()):>7,} rows")
    for i, biz in enumerate(businesses):
        print(f"    #{i} {biz['vertical']:14s} {biz['scenario']:18s} {biz['name']}")


if __name__ == "__main__":
    raise SystemExit(main())
