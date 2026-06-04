"""Competitor share aggregation from auction-insight rows.

Auction Insights are collected per (campaign, competitor domain, day). For both
LLM context and the launch competitor scan we want the account-level top
competitors. ``top_competitors`` reduces raw rows to the strongest domains by
impression share (max across campaigns) — a pure function, shared by the
account-context builder and the launch proposal flow.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompetitorShare:
    domain: str
    impression_share: float  # 0..1, the domain's max search impression share


def top_competitors(rows: list[dict], limit: int = 5) -> list[CompetitorShare]:
    """Top competitors by impression share from auction-insight rows.

    Each row is expected to have ``competitor_domain`` and ``impression_share``.
    Missing/empty domains are skipped. Returns at most ``limit``, descending.
    """
    domain_is: dict[str, float] = {}
    for r in rows:
        domain = r.get("competitor_domain")
        if not domain:
            continue
        is_val = r.get("impression_share") or 0.0
        if is_val > domain_is.get(domain, 0.0):
            domain_is[domain] = is_val

    ranked = sorted(domain_is.items(), key=lambda kv: -kv[1])[:limit]
    return [CompetitorShare(domain=d, impression_share=round(v, 4)) for d, v in ranked]
