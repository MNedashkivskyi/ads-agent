"""Phase 3.6 — creative API end-to-end: generate → select → finalize (no DB).

Drives the real creative router with an in-memory flow over fake LLM
generator/judge, and asserts the finalized RSA is valid and every shipped asset
is tagged by angle.
"""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.campaign_intelligence.creatives.finalize_hook_set import (
    FinalizeHookSetUseCase,
)
from adcopilot.application.use_cases.campaign_intelligence.creatives.generate_hooks import (
    GenerateHooksUseCase,
)
from adcopilot.application.use_cases.campaign_intelligence.creatives.select_hooks import (
    SelectHooksUseCase,
)
from adcopilot.domain.campaign_intelligence.creatives.hook_candidate import HookStatus
from adcopilot.domain.campaign_intelligence.creatives.hook_run import HookRun
from tests.unit.application.campaign_intelligence._fakes import (
    FakeHookGenerator,
    FakeHookJudge,
    FakeHookRepository,
)

_USER = "user-xyz"


class InMemoryCreativeFlow:
    def __init__(self) -> None:
        self.repo = FakeHookRepository()
        self.generator = FakeHookGenerator()
        self.judge = FakeHookJudge(winner_angle="PAIN")

    async def generate(self, *, campaign_id, user_id, account_id=None, vertical=None,
                       language=None, service=None, problems=None):  # noqa: ANN001
        run = HookRun(
            campaign_id=campaign_id,
            account_id=account_id or "acct-1",
            user_id=user_id,
            vertical=vertical or "salon",
            language=language or "pl",
            service=service or "icoone",
            problems=problems or [],
        )
        await self.repo.create_run(run)
        await GenerateHooksUseCase(self.generator, self.repo).run(run)
        return run.id

    async def select(self, *, campaign_id, user_id):  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        await SelectHooksUseCase(self.judge, self.repo).run(run)
        return run.id

    async def finalize(self, *, campaign_id, user_id):  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        await FinalizeHookSetUseCase(self.repo).run(run, customer_id="123-456-7890")
        return run.id

    async def get_status(self, *, campaign_id, user_id):  # noqa: ANN001
        run = await self.repo.get_latest_run_for_campaign(campaign_id, user_id)
        if run is None:
            return None, None, None
        return run.status.value, run.id, run.rsa_payload


@pytest.fixture
def client():  # noqa: ANN201
    from fastapi.testclient import TestClient

    from adcopilot.interfaces.api.auth_middleware import get_current_user
    from adcopilot.interfaces.api.cie_creatives import get_creative_flow
    from adcopilot.main import create_app

    flow = InMemoryCreativeFlow()
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_creative_flow] = lambda: flow
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, flow
    app.dependency_overrides.clear()


def test_creative_flow_generate_select_finalize(client) -> None:  # noqa: ANN001
    c, flow = client
    cid = "22222222-2222-2222-2222-222222222222"

    resp = c.post(
        f"/api/campaigns/{cid}/creatives/generate",
        json={"account_id": "acct-1", "vertical": "salon", "service": "icoone"},
    )
    assert resp.status_code == 202, resp.text

    assert c.get(f"/api/campaigns/{cid}/creatives/status").json()["status"] == "ready"

    assert c.post(f"/api/campaigns/{cid}/creatives/select").status_code == 202
    assert c.post(f"/api/campaigns/{cid}/creatives/finalize").status_code == 202

    status = c.get(f"/api/campaigns/{cid}/creatives/status").json()
    assert status["status"] == "finalized"
    payload = status["rsa_payload"]
    assert payload is not None
    assert len(payload["headlines"]) >= 3
    assert len(payload["descriptions"]) >= 2
    # Pinning + angle tags present on the RSA.
    assert any(a.get("pinned_field") == "HEADLINE_1" for a in payload["headlines"])
    assert all("angle" in a for a in payload["headlines"])

    # Every shipped asset persisted with its angle (Phase 4 attribution gate).
    assert flow.repo.shipped_assets
    assert all(a["angle"] for a in flow.repo.shipped_assets)


def test_select_marks_candidates_and_keeps_angle_diversity(client) -> None:  # noqa: ANN001
    c, flow = client
    cid = "33333333-3333-3333-3333-333333333333"
    c.post(
        f"/api/campaigns/{cid}/creatives/generate",
        json={"account_id": "acct-1", "vertical": "salon"},
    )
    c.post(f"/api/campaigns/{cid}/creatives/select")
    run = list(flow.repo.runs.values())[-1]
    selected = [
        x for x in flow.repo.candidates[run.id] if x.status is HookStatus.SELECTED
    ]
    angles = {x.angle for x in selected}
    assert len(angles) > 1  # diversity preserved across angles
