"""Use case: generate custom intent audience clusters from top converting search terms."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.infrastructure.db.models import SearchTermSnapshotModel

logger = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 30
_TOP_N = 50
_PROMPT_KEY = "custom_intent_v1"
_SYSTEM = (
    "Jesteś ekspertem Google Ads specjalizującym się w tworzeniu niestandardowych list odbiorców "
    "opartych na intencji. Odpowiadaj wyłącznie po polsku. Grupuj frazy tematycznie i nadawaj "
    "klastrom zwięzłe, opisowe nazwy."
)
_FALLBACK_PROMPT = (
    "Pogrupuj poniższe frazy wyszukiwania w klastry tematyczne (max 5 klastrów). "
    "Dla każdego klastra podaj: nazwę (max 5 słów) i listę fraz. "
    "Następnie napisz krótką rekomendację (2–3 zdania) jak wykorzystać te klastry "
    "w niestandardowych listach odbiorców Google Ads.\n\n"
    "Odpowiedz w formacie JSON:\n"
    '{{"clusters": [{{"name": "...", "terms": ["..."]}}], "recommendations_pl": "..."}}\n\n'
    "Frazy:\n{search_terms}"
)


async def generate_custom_intent_audience(
    account_id: str,
    session: AsyncSession,
    llm: LLMClient,
    prompt_repo: PromptVersionRepository,
) -> dict:
    """Cluster top converting search terms into custom intent audience themes."""
    log = logger.bind(account_id=account_id)
    log.info("generate_custom_intent_audience.start")

    acct_uuid = uuid.UUID(account_id)
    cutoff = (datetime.now(tz=UTC) - timedelta(days=_LOOKBACK_DAYS)).date()

    # -------------------------------------------------------------------------
    # 1. Query top 50 converting search terms
    # -------------------------------------------------------------------------
    stmt = (
        select(
            SearchTermSnapshotModel.search_term,
            SearchTermSnapshotModel.conversions,
            SearchTermSnapshotModel.clicks,
            SearchTermSnapshotModel.cost_micros,
        )
        .where(
            SearchTermSnapshotModel.account_id == acct_uuid,
            SearchTermSnapshotModel.snapshot_date >= cutoff,
            SearchTermSnapshotModel.conversions > 0,
        )
        .order_by(SearchTermSnapshotModel.conversions.desc())
        .limit(_TOP_N)
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        log.info("generate_custom_intent_audience.no_data")
        return {
            "account_id": account_id,
            "search_terms": [],
            "clusters": [],
            "recommendations_pl": (
                "Brak danych o konwertujących frazach wyszukiwania w analizowanym okresie. "
                "Upewnij się, że śledzenie konwersji jest poprawnie skonfigurowane i aktywne, "
                "a dane snapshot są aktualne."
            ),
            "analyzed_at": datetime.now(tz=UTC).isoformat(),
        }

    search_terms = [r.search_term for r in rows]

    # -------------------------------------------------------------------------
    # 2. Get prompt template
    # -------------------------------------------------------------------------
    try:
        prompt_template = await prompt_repo.get_latest(_PROMPT_KEY)
        if prompt_template:
            prompt_text = prompt_template.content.format(
                search_terms="\n".join(f"- {t}" for t in search_terms)
            )
        else:
            prompt_text = _FALLBACK_PROMPT.format(
                search_terms="\n".join(f"- {t}" for t in search_terms)
            )
    except Exception:
        prompt_text = _FALLBACK_PROMPT.format(
            search_terms="\n".join(f"- {t}" for t in search_terms)
        )

    # -------------------------------------------------------------------------
    # 3. Call Claude Haiku
    # -------------------------------------------------------------------------
    raw_response = await llm.complete(
        system=_SYSTEM,
        user=prompt_text,
        max_tokens=800,
        temperature=0.3,
    )

    # -------------------------------------------------------------------------
    # 4. Parse response — expect JSON with clusters + recommendations_pl
    # -------------------------------------------------------------------------
    clusters: list[dict] = []
    recommendations_pl: str = raw_response.strip()

    try:
        # Strip markdown code fence if present
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = clean.split("```", 2)[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean)
        clusters = parsed.get("clusters", [])
        recommendations_pl = parsed.get("recommendations_pl", raw_response.strip())
    except (json.JSONDecodeError, ValueError):
        # LLM returned free text — keep it as-is, clusters remain empty
        log.warning("generate_custom_intent_audience.parse_failed", raw=raw_response[:200])

    analyzed_at = datetime.now(tz=UTC).isoformat()
    log.info(
        "generate_custom_intent_audience.done",
        search_terms=len(search_terms),
        clusters=len(clusters),
    )

    return {
        "account_id": account_id,
        "search_terms": search_terms,
        "clusters": clusters,
        "recommendations_pl": recommendations_pl,
        "analyzed_at": analyzed_at,
    }
