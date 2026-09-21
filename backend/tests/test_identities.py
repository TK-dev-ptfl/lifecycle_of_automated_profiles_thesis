import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.pipelines.email_pool.registry import ProviderPipeline
from app.services import identity_service


@pytest.fixture
async def email_platform(client, auth_headers):
    # Name deliberately doesn't match any entry in the automated-provider
    # registry (only "tuta" is registered) - the background email pipeline
    # then fails fast with a clear "no pipeline for this provider" error
    # instead of launching a real browser during tests.
    resp = await client.post(
        "/api/email-platforms",
        json={"type": "classic", "name": "test-provider", "domain": "example.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_create_identity(client, auth_headers):
    resp = await client.post(
        "/api/identities",
        json={
            "display_name": "Alice Smith",
            "username": "alice_smith_001",
            "email": "alice@tempmail.fake",
            "email_provider": "mail.tm",
            "location": "US",
            "age": 28,
            "password": "secret123",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice_smith_001"
    assert data["status"] == "fresh"


@pytest.mark.asyncio
async def test_generate_identity(client, auth_headers, email_platform):
    resp = await client.post(
        "/api/identities/generate",
        json={"email_platform_id": email_platform["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "username" in data
    assert data["status"] == "fresh"
    assert data["email"] is None  # attached later by the (here: unregistered) email pipeline


@pytest.mark.asyncio
async def test_generate_identity_requires_email_platform(client, auth_headers):
    resp = await client.post("/api/identities/generate", json={}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_identities(client, auth_headers, email_platform):
    await client.post(
        "/api/identities/generate",
        json={"email_platform_id": email_platform["id"]},
        headers=auth_headers,
    )
    resp = await client.get("/api/identities", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_filter_identities_by_status(client, auth_headers):
    resp = await client.get("/api/identities?status=fresh", headers=auth_headers)
    assert resp.status_code == 200
    for identity in resp.json():
        assert identity["status"] == "fresh"


@pytest.mark.asyncio
async def test_update_identity(client, auth_headers, email_platform):
    create = await client.post(
        "/api/identities/generate",
        json={"email_platform_id": email_platform["id"]},
        headers=auth_headers,
    )
    identity_id = create.json()["id"]
    resp = await client.patch(
        f"/api/identities/{identity_id}",
        json={"status": "active", "bio": "Updated bio"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_identity(client, auth_headers, email_platform):
    create = await client.post(
        "/api/identities/generate",
        json={"email_platform_id": email_platform["id"]},
        headers=auth_headers,
    )
    identity_id = create.json()["id"]
    resp = await client.delete(f"/api/identities/{identity_id}", headers=auth_headers)
    assert resp.status_code == 204
    get = await client.get(f"/api/identities/{identity_id}", headers=auth_headers)
    assert get.status_code == 404


@pytest.mark.asyncio
async def test_pipeline_status_reflects_unsupported_provider(client, auth_headers, email_platform):
    create = await client.post(
        "/api/identities/generate",
        json={"email_platform_id": email_platform["id"]},
        headers=auth_headers,
    )
    identity_id = create.json()["id"]
    resp = await client.get(f"/api/identities/{identity_id}/pipeline-status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "test-provider" in data["error"]


@pytest.mark.asyncio
async def test_manual_step_resumes_via_gate_not_stdin():
    """Regression test for the bug where the CAPTCHA step waited on the
    backend process's own stdin (input()) - which raised EOFError instantly
    on a backgrounded server and closed the browser. Simulates a provider
    that pauses on its manual step exactly like Tuta's does, but with no
    real browser involved, and checks that:
      1. the pipeline actually reaches 'waiting_manual' and stays there
      2. resume_pipeline() (the "Continue" button's endpoint) unblocks it
      3. it then runs to completion
    """
    identity_id = uuid.uuid4()  # deliberately not persisted - see final assertion below
    fake_step = SimpleNamespace(name="fake_manual_step", manual=True)
    reached_manual = asyncio.Event()

    async def fake_run(on_step=None, wait_for_manual=None, **_):
        if on_step:
            on_step(0, fake_step)
        reached_manual.set()
        await wait_for_manual("test prompt")
        return SimpleNamespace(username="resolved-user", password="resolved-pass")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [{"name": "fake_manual_step", "manual": True}])

    # Bypass proxy selection entirely - it hits the real (production, not
    # test-isolated) Proxy table via AsyncSessionLocal, same as the identity
    # DB-attach step below. Not what this test is about, and mutating real
    # proxy rows' is_healthy/last_checked as a side effect of running the
    # suite would be its own kind of test pollution.
    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", return_value=None):
        task = asyncio.create_task(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            )
        )
        try:
            await asyncio.wait_for(reached_manual.wait(), timeout=5)

            status = identity_service.get_pipeline_status(identity_id)
            assert status["status"] == "waiting_manual"
            assert status["manual"] is True

            resumed = identity_service.resume_pipeline(identity_id)
            assert resumed is True

            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()

    # identity_id was never actually persisted, so the DB-attach step reports
    # "identity no longer exists" rather than "completed" - what matters for
    # this regression test is that the pipeline reached and left
    # 'waiting_manual' via resume_pipeline() rather than hanging or crashing.
    final_status = identity_service.get_pipeline_status(identity_id)
    assert final_status["status"] == "failed"
    assert final_status["error"] == "identity no longer exists"


@pytest.mark.asyncio
async def test_resume_pipeline_returns_false_when_nothing_waiting():
    assert identity_service.resume_pipeline(uuid.uuid4()) is False


@pytest.mark.asyncio
async def test_two_pipelines_run_concurrently_not_one_after_another():
    """There used to be a process-wide lock serializing every pipeline run
    (back when the CAPTCHA step blocked on this process's own stdin and two
    browsers would've fought over one prompt). That's gone - each identity
    now waits on its own manual_gate entry, so two pipelines should both be
    able to reach 'waiting_manual' at the same time instead of the second
    one queueing behind the first."""
    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    reached = {id_a: asyncio.Event(), id_b: asyncio.Event()}

    fake_step = SimpleNamespace(name="fake_manual_step", manual=True)

    def make_fake_run(identity_id):
        async def fake_run(on_step=None, wait_for_manual=None, **_):
            if on_step:
                on_step(0, fake_step)
            reached[identity_id].set()
            await wait_for_manual("test prompt")
            return SimpleNamespace(username=f"user-{identity_id}", password="pw")
        return fake_run

    fake_provider_a = ProviderPipeline(run=make_fake_run(id_a), describe=lambda: [])
    fake_provider_b = ProviderPipeline(run=make_fake_run(id_b), describe=lambda: [])
    providers = {"a": fake_provider_a, "b": fake_provider_b}

    with patch("app.services.identity_service.get_provider_pipeline", side_effect=lambda name: providers[name]), \
         patch("app.services.identity_service._select_and_test_proxy", return_value=None):
        task_a = asyncio.create_task(
            identity_service.start_email_pipeline_for_identity(id_a, "a", "example.com", uuid.uuid4(), "classic")
        )
        task_b = asyncio.create_task(
            identity_service.start_email_pipeline_for_identity(id_b, "b", "example.com", uuid.uuid4(), "classic")
        )
        try:
            # If these were still serialized, B would never reach
            # 'waiting_manual' until A was resumed - so waiting on both
            # concurrently with a short timeout proves they're running in
            # parallel, not queued.
            await asyncio.wait_for(asyncio.gather(reached[id_a].wait(), reached[id_b].wait()), timeout=5)

            assert identity_service.get_pipeline_status(id_a)["status"] == "waiting_manual"
            assert identity_service.get_pipeline_status(id_b)["status"] == "waiting_manual"

            assert identity_service.resume_pipeline(id_a) is True
            assert identity_service.resume_pipeline(id_b) is True
            await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=5)
        finally:
            for t in (task_a, task_b):
                if not t.done():
                    t.cancel()


@pytest.mark.asyncio
async def test_concurrent_claims_never_double_assign_the_same_free_proxy():
    """Regression test for the race the atomic DELETE...WHERE guard in
    _claim_and_consume_free_proxy exists to prevent: with the process-wide
    lock removed, two identities' pipelines could otherwise both see the
    same free proxy as a candidate and both try to use it. Tests the atomic
    claim primitive directly (rather than _select_and_test_proxy, which
    retries the next candidate on a lost race - both callers legitimately
    succeeding with *different* proxies when the pool has several is correct
    behavior, not what this test is checking): with only one proxy to fight
    over, exactly one of two concurrent claims on it should succeed."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="198.51.100.7", port=3128, protocol=ProxyProtocol.http, type=ProxyType.datacenter,
            country="ZZ", provider="race-test",
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as db_a, AsyncSessionLocal() as db_b:
        claimed_a, claimed_b = await asyncio.gather(
            identity_service._claim_and_consume_free_proxy(db_a, proxy_id, id_a),
            identity_service._claim_and_consume_free_proxy(db_b, proxy_id, id_b),
        )

    assert {claimed_a, claimed_b} == {True, False}, "exactly one of the two concurrent claims should win"

    async with AsyncSessionLocal() as db:
        assert await db.get(Proxy, proxy_id) is None  # consumed either way - removed from the pool
