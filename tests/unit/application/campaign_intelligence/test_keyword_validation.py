"""Phase 1.7 — validation orchestration: cache → KP → bucketed-guard → DataForSEO."""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
    ValidateKeywordVolumesUseCase,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent
from adcopilot.domain.exceptions import GoogleAdsRateLimited
from adcopilot.infrastructure.cache.keyword_volume_cache import KeywordVolumeCache
from tests.unit.application.campaign_intelligence._fakes import (
    FakeKeywordRepository,
    FakeRedis,
    FakeVolumePort,
    make_volume,
)


async def _noop_sleep(_: float) -> None:
    return None


async def _seed_run(repo: FakeKeywordRepository, phrases: dict[str, KeywordIntent]) -> KeywordRun:
    run = KeywordRun(campaign_id="c1", account_id="a1", user_id="u1", vertical="salon")
    await repo.create_run(run)
    candidates = [
        KeywordCandidate(phrase=p, intent=intent) for p, intent in phrases.items()
    ]
    await repo.replace_candidates(run.id, run.campaign_id, candidates)
    return run


def _cache(redis: FakeRedis) -> KeywordVolumeCache:
    return KeywordVolumeCache(redis, ttl_seconds=3600)


async def test_bucketed_kp_routes_only_that_phrase_to_dataforseo() -> None:
    repo = FakeKeywordRepository()
    run = await _seed_run(
        repo,
        {"drenaż limfatyczny": KeywordIntent.INTENT, "icoone warszawa": KeywordIntent.BRAND},
    )
    # KP returns an exact number for one phrase, a bucketed (range-only) for the other.
    kp = FakeVolumePort(
        {
            "drenaż limfatyczny": make_volume(8000),
            "icoone warszawa": make_volume(0, bucketed=True),
        },
        name="kp",
    )
    df = FakeVolumePort({"icoone warszawa": make_volume(40)}, name="dataforseo")

    use_case = ValidateKeywordVolumesUseCase(
        cache=_cache(FakeRedis()), primary=kp, fallback=df, repo=repo, sleep=_noop_sleep
    )
    await use_case.run(run)

    # Only the bucketed phrase was routed to DataForSEO.
    assert df.requested == ["icoone warszawa"]
    assert "drenaż limfatyczny" not in df.requested
    cands = {c.phrase: c for c in await repo.list_candidates(run.id)}
    assert cands["drenaż limfatyczny"].status is KeywordStatus.VALIDATED
    assert cands["icoone warszawa"].status is KeywordStatus.VALIDATED
    assert run.status is KeywordRunStatus.READY


async def test_non_viable_volume_is_rejected() -> None:
    repo = FakeKeywordRepository()
    run = await _seed_run(repo, {"rzadkie zapytanie": KeywordIntent.PROBLEM})
    kp = FakeVolumePort({"rzadkie zapytanie": make_volume(3)}, name="kp")
    df = FakeVolumePort({}, name="dataforseo")
    use_case = ValidateKeywordVolumesUseCase(
        cache=_cache(FakeRedis()), primary=kp, fallback=df, repo=repo,
        min_viable_volume=10, sleep=_noop_sleep,
    )
    await use_case.run(run)
    cand = (await repo.list_candidates(run.id))[0]
    assert cand.status is KeywordStatus.REJECTED


async def test_cache_hit_skips_api_calls() -> None:
    repo = FakeKeywordRepository()
    redis = FakeRedis()
    # First run populates the cache.
    run1 = await _seed_run(repo, {"drenaż limfatyczny": KeywordIntent.INTENT})
    kp = FakeVolumePort({"drenaż limfatyczny": make_volume(8000)}, name="kp")
    df = FakeVolumePort({}, name="dataforseo")
    uc = ValidateKeywordVolumesUseCase(
        cache=_cache(redis), primary=kp, fallback=df, repo=repo, sleep=_noop_sleep
    )
    await uc.run(run1)
    assert kp.call_count == 1

    # Second run for the same phrase: cache hit → no KP/DataForSEO calls.
    run2 = await _seed_run(repo, {"drenaż limfatyczny": KeywordIntent.INTENT})
    kp2 = FakeVolumePort({"drenaż limfatyczny": make_volume(8000)}, name="kp")
    df2 = FakeVolumePort({}, name="dataforseo")
    uc2 = ValidateKeywordVolumesUseCase(
        cache=_cache(redis), primary=kp2, fallback=df2, repo=repo, sleep=_noop_sleep
    )
    await uc2.run(run2)
    assert kp2.call_count == 0  # cache hit — adapter not invoked
    assert df2.call_count == 0


async def test_keep_all_validates_even_without_volume() -> None:
    # The launch step keeps every candidate so the comparison is always populated,
    # even when the volume APIs return nothing.
    repo = FakeKeywordRepository()
    run = await _seed_run(
        repo, {"drenaż limfatyczny": KeywordIntent.INTENT, "nieznana fraza": KeywordIntent.PROBLEM}
    )
    kp = FakeVolumePort({"drenaż limfatyczny": make_volume(8000)}, name="kp")
    df = FakeVolumePort({}, name="dataforseo")  # nothing else resolves
    use_case = ValidateKeywordVolumesUseCase(
        cache=_cache(FakeRedis()), primary=kp, fallback=df, repo=repo,
        min_viable_volume=10, keep_all=True, sleep=_noop_sleep,
    )
    await use_case.run(run)
    cands = {c.phrase: c for c in await repo.list_candidates(run.id)}
    # Both kept as validated; the resolved one carries its real volume.
    assert cands["drenaż limfatyczny"].status is KeywordStatus.VALIDATED
    assert cands["drenaż limfatyczny"].volume.monthly_searches == 8000
    assert cands["nieznana fraza"].status is KeywordStatus.VALIDATED
    assert cands["nieznana fraza"].volume.monthly_searches == 0


async def test_rate_limit_retries_then_fails_cleanly() -> None:
    repo = FakeKeywordRepository()
    run = await _seed_run(repo, {"x": KeywordIntent.INTENT})

    class AlwaysRateLimited:
        name = "kp"

        def __init__(self) -> None:
            self.call_count = 0

        async def fetch_volumes(self, phrases, ctx):  # noqa: ANN001
            self.call_count += 1
            raise GoogleAdsRateLimited("quota")

    kp = AlwaysRateLimited()
    df = FakeVolumePort({}, name="dataforseo")
    uc = ValidateKeywordVolumesUseCase(
        cache=_cache(FakeRedis()), primary=kp, fallback=df, repo=repo, sleep=_noop_sleep
    )
    with pytest.raises(GoogleAdsRateLimited):
        await uc.run(run)
    assert kp.call_count == 3  # retried with backoff, then gave up
    assert run.status is KeywordRunStatus.FAILED
