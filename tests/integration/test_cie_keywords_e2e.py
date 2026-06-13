"""Phase 1.10 — keyword API end-to-end with external ports mocked (no DB).

Drives generate → validate → status → comparison through the real FastAPI router,
swapping an in-memory flow (fake repo + fake LLM generator + fake volume ports) in
for the DB+Celery one. Asserts the bucketed → DataForSEO fallback path fires, the
status transitions to ready, and the comparison proves INTENT ≫ BRAND.
"""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.campaign_intelligence.keywords.generate_keyword_candidates import (  # noqa: E501
    GenerateKeywordCandidatesUseCase,
)
from adcopilot.application.use_cases.campaign_intelligence.keywords.rank_keywords import (
    RankKeywordsUseCase,
)
from adcopilot.application.use_cases.campaign_intelligence.keywords.validate_keyword_volumes import (  # noqa: E501
    ValidateKeywordVolumesUseCase,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import KeywordComparison
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import KeywordRun
from tests.unit.application.campaign_intelligence._fakes import (
    FakeKeywordGenerator,
    FakeKeywordRepository,
    FakeRedis,
    FakeVolumePort,
    make_volume,
)
from adcopilot.infrastructure.cache.keyword_volume_cache import KeywordVolumeCache

_USER = "user-123"

# icoone-shaped fixture: brand terms gray, intent/problem terms carry the volume.
_GENERATED = {
    "BRAND": ["icoone warszawa", "icoone cena"],
    "INTENT": ["drenaż limfatyczny", "modelowanie sylwetki"],
    "PROBLEM": ["jak pozbyć się cellulitu"],
}
_KP_VOLUMES = {
    "icoone warszawa": make_volume(0, bucketed=True),  # fresh account → bucketed
    "icoone cena": make_volume(30),
    "drenaż limfatyczny": make_volume(8000),
    "modelowanie sylwetki": make_volume(4000),
    "jak pozbyć się cellulitu": make_volume(6000),
}
_DATAFORSEO_VOLUMES = {"icoone warszawa": make_volume(40)}  # exact fallback


class InMemoryKeywordFlow:
    """Runs the real use cases synchronously over in-memory fakes."""

    def __init__(self) -> None:
        self.repo = FakeKeywordRepository()
        self.generator = FakeKeywordGenerator(_GENERATED)
        self.redis = FakeRedis()
        self.kp = FakeVolumePort(_KP_VOLUMES, name="kp")
        self.df = FakeVolumePort(_DATAFORSEO_VOLUMES, name="dataforseo")

    async def generate(self, *, campaign_id, user_id, account_id=None, vertical=None,
                       language=None, service=None, problems=None, seeds=None) -> str:  # noqa: ANN001
        run = KeywordRun(
            campaign_id=campaign_id,
            account_id=account_id or "acct-1",
            user_id=user_id,
            vertical=vertical or "salon",
            language=language or "pl",
            service=service or "icoone",
            problems=problems or [],
            seeds=seeds or [],
        )
        await self.repo.create_run(run)
        await GenerateKeywordCandidatesUseCase(self.generator, self.repo).run(run)
        return run.id  # type: ignore[return-value]

    async def validate(self, *, campaign_id, user_id) -> str:  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        assert run is not None
        uc = ValidateKeywordVolumesUseCase(
            cache=KeywordVolumeCache(self.redis, 3600),
            primary=self.kp,
            fallback=self.df,
            repo=self.repo,
        )
        await uc.run(run)
        return run.id  # type: ignore[return-value]

    async def get_status(self, *, campaign_id, user_id):  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        if run is None:
            return None, None
        return run.status.value, run.id

    async def comparison(self, *, campaign_id, user_id) -> KeywordComparison | None:  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        if run is None:
            return None
        return await RankKeywordsUseCase(self.repo).run(run.id)


@pytest.fixture
def client():  # noqa: ANN201
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.interfaces.api.cie_keywords import get_keyword_flow
    from adcopilot.main import create_app

    flow = InMemoryKeywordFlow()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_keyword_flow] = lambda: flow
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, flow
    app.dependency_overrides.clear()


def test_keyword_flow_generate_validate_comparison(client) -> None:  # noqa: ANN001
    c, flow = client
    cid = "11111111-1111-1111-1111-111111111111"

    # generate → 202 + generating
    resp = c.post(
        f"/api/campaigns/{cid}/keywords/generate",
        json={"account_id": "acct-1", "vertical": "salon", "service": "icoone"},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "generating"

    # status after generate
    resp = c.get(f"/api/campaigns/{cid}/keywords/status")
    assert resp.json()["status"] == "generated"

    # validate → 202; in-memory flow runs synchronously to ready
    resp = c.post(f"/api/campaigns/{cid}/keywords/validate")
    assert resp.status_code == 202, resp.text

    resp = c.get(f"/api/campaigns/{cid}/keywords/status")
    assert resp.json()["status"] == "ready"

    # Fallback path fired: the bucketed phrase was routed to DataForSEO only.
    assert flow.df.requested == ["icoone warszawa"]

    # comparison proves INTENT/PROBLEM ≫ BRAND
    resp = c.get(f"/api/campaigns/{cid}/keywords/comparison")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["intent_total_volume"] > body["brand_total_volume"]
    intents = {g["intent"] for g in body["groups"]}
    assert intents == {"BRAND", "INTENT", "PROBLEM"}
    assert body["verdict"]


def test_comparison_404_when_no_run(client) -> None:  # noqa: ANN001
    c, _ = client
    resp = c.get("/api/campaigns/no-run/keywords/comparison")
    assert resp.status_code == 404
