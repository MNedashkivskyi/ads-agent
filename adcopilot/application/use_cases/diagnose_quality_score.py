"""Quality Score diagnostic use case — returns per-keyword QS breakdown with LLM tips."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.config import get_settings
from adcopilot.infrastructure.db.models import KeywordSnapshotModel

logger = structlog.get_logger(__name__)

_QS_RATING = {
    "ABOVE_AVERAGE": "powyżej średniej",
    "AVERAGE": "średni",
    "BELOW_AVERAGE": "poniżej średniej",
}

_LLM_PROMPT = """Jesteś ekspertem Google Ads. Oto wyniki Quality Score dla słów kluczowych użytkownika:

{keyword_lines}

Na podstawie powyższych danych napisz krótką (3-5 zdań), konkretną diagnozę po polsku i zasugeruj najważniejsze działania naprawcze. Skup się na słowach kluczowych z najniższymi ocenami."""


@dataclass
class KeywordQSDiagnosis:
    criterion_id: int
    text: str
    match_type: str
    quality_score: int | None
    expected_ctr: str | None
    ad_relevance: str | None
    landing_page_experience: str | None
    impressions: int


@dataclass
class QSDiagnosisResult:
    keywords: list[KeywordQSDiagnosis]
    llm_summary: str | None
    avg_quality_score: float | None


async def diagnose_quality_score(
    account_id: str,
    session: AsyncSession,
    limit: int = 50,
) -> QSDiagnosisResult:
    result = await session.execute(
        select(KeywordSnapshotModel)
        .where(KeywordSnapshotModel.account_id == account_id)
        .where(KeywordSnapshotModel.quality_score.isnot(None))
        .order_by(
            text("snapshot_date DESC"),
            KeywordSnapshotModel.impressions.desc(),
        )
        .limit(limit)
    )
    rows = list(result.scalars().all())

    keywords = [
        KeywordQSDiagnosis(
            criterion_id=r.criterion_id,
            text=r.text,
            match_type=r.match_type,
            quality_score=r.quality_score,
            expected_ctr=r.expected_ctr,
            ad_relevance=r.ad_relevance,
            landing_page_experience=r.landing_page_experience,
            impressions=r.impressions,
        )
        for r in rows
    ]

    avg_qs: float | None = None
    if keywords:
        scores = [k.quality_score for k in keywords if k.quality_score is not None]
        avg_qs = sum(scores) / len(scores) if scores else None

    llm_summary = await _generate_llm_summary(keywords)

    return QSDiagnosisResult(keywords=keywords, llm_summary=llm_summary, avg_quality_score=avg_qs)


async def _generate_llm_summary(keywords: list[KeywordQSDiagnosis]) -> str | None:
    if not keywords:
        return None
    try:
        import anthropic

        settings = get_settings()

        def _rating(val: str | None) -> str:
            return _QS_RATING.get(val or "", "brak danych")

        lines = []
        for kw in keywords[:20]:
            lines.append(
                f"- \"{kw.text}\" ({kw.match_type}): QS={kw.quality_score}, "
                f"CTR={_rating(kw.expected_ctr)}, "
                f"Trafność reklamy={_rating(kw.ad_relevance)}, "
                f"Str. docelowa={_rating(kw.landing_page_experience)}, "
                f"wyśw.={kw.impressions}"
            )

        prompt = _LLM_PROMPT.format(keyword_lines="\n".join(lines))
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else None
    except Exception as exc:
        logger.warning("qs_llm_summary_failed", error=str(exc))
        return None
