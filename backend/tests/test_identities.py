import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.pipelines.email_pool.registry import ProviderPipeline
from app.services import identity_service


def _fake_proxy() -> SimpleNamespace:
    """A stand-in Proxy for tests that mock out _select_and_test_proxy - a
    proxy is now mandatory (start_email_pipeline_for_identity refuses to run
    a single pipeline action without one), so these can no longer just mock
    it to return_value=None the way they used to when a proxy was optional;
    that would make the pipeline fail before provider.run() is ever called,
    which isn't what those tests are actually about. Has every attribute
    _proxy_to_playwright_config, the proxy-found log line, and retire_proxy
    touch."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        host="203.0.113.1", port=8080, username=None, password=None,
        protocol=SimpleNamespace(value="http"), type=SimpleNamespace(value="residential"), country="US",
    )


@pytest.fixture
async def email_platform(client, auth_headers):
    # Named for a provider that IS in the automated-provider registry: creating
    # an identity without an email is now refused outright (422) for a provider
    # with no pipeline behind it, rather than being accepted and then quietly
    # cleaned up. Nothing actually runs - conftest's autouse queued_pipelines
    # fixture intercepts the hand-off to the scheduler.
    resp = await client.post(
        "/api/email-platforms",
        json={"type": "temporary", "name": "tuta", "domain": "tuta.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
async def unautomated_email_platform(client, auth_headers):
    """A platform whose name matches no registered signup pipeline."""
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
    assert data["email"] is None  # attached later, once the queued pipeline runs


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
async def test_unautomated_provider_is_refused_before_any_identity_is_written(
    client, auth_headers, unautomated_email_platform, queued_pipelines
):
    """A provider with no signup pipeline behind it is rejected up front rather
    than accepted and then cleaned up. It used to be the latter: the identity
    was created, the pipeline failed immediately with "no pipeline for this
    provider", and the identity was deleted again - a confusing round trip for
    something knowable from the request alone."""
    before = await client.get("/api/identities", headers=auth_headers)
    resp = await client.post(
        "/api/identities/generate",
        json={"email_platform_id": unautomated_email_platform["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "test-provider" in resp.json()["detail"]
    assert queued_pipelines == []
    after = await client.get("/api/identities", headers=auth_headers)
    assert len(after.json()) == len(before.json())


@pytest.mark.asyncio
async def test_creating_an_identity_queues_it_instead_of_starting_a_pipeline(
    client, auth_headers, email_platform, queued_pipelines
):
    """The request returns as soon as the row is written - it must not wait on a
    proxy search or a browser. All it does is hand the identity to the
    scheduler, which caps how many pipelines run at once."""
    resp = await client.post(
        "/api/identities",
        json={
            "display_name": "Queued Person",
            "username": "queued_person_001",
            "location": "US",
            "age": 31,
            "password": "secret123",
            "email_platform_id": email_platform["id"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    identity_id = resp.json()["id"]

    assert len(queued_pipelines) == 1
    queued_identity_id, queued_platform_id, provider_name = queued_pipelines[0]
    assert str(queued_identity_id) == identity_id
    assert str(queued_platform_id) == email_platform["id"]
    assert provider_name == "tuta"


@pytest.mark.asyncio
async def test_identity_with_a_pooled_email_is_not_queued(client, auth_headers, queued_pipelines):
    """Supplying an existing address means there's no mailbox to create, so
    there's nothing for the scheduler to do."""
    resp = await client.post(
        "/api/identities",
        json={
            "display_name": "Has Mail",
            "username": "has_mail_001",
            "email": "has.mail@tempmail.fake",
            "email_provider": "mail.tm",
            "location": "US",
            "age": 24,
            "password": "secret123",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert queued_pipelines == []


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

    # Bypass proxy selection and the pool-refresh scrape entirely - both hit
    # real external things (the production Proxy table via AsyncSessionLocal,
    # same as the identity DB-attach step below, and free-proxy-list.net
    # itself) that aren't what this test is about. Real network calls in a
    # unit test are slow/flaky/offline-unsafe, and mutating real proxy rows
    # as a side effect of running the suite would be its own kind of test
    # pollution.
    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", return_value=_fake_proxy()), \
         patch("app.services.proxy_service.import_proxies_from_free_list", return_value={"imported": 0, "skipped": 0}):
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
async def test_failed_pipeline_deletes_the_identity():
    """A failed signup leaves no real account behind it - the identity
    itself should be deleted (see identity_service._delete_failed_identity),
    while the failure and its details stay visible via pipeline_progress
    (which is self-contained - display_name/error are stored on the record
    directly, not looked up live from the now-gone Identity row).

    Uses AsyncSessionLocal directly rather than the HTTP test client: the
    pipeline runs via start_email_pipeline_for_identity, which opens its own
    session against the production AsyncSessionLocal (by design - the
    request-scoped session is long closed by the time a multi-minute
    pipeline finishes), not the test client's overridden in-memory session -
    so creating the identity through the test client wouldn't make it
    visible to the code under test here.
    """
    from app.database import AsyncSessionLocal, Base, engine
    from app.auth.utils import hash_password
    from app.models.identity import Identity, IdentityStatus

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        identity = Identity(
            display_name="Doomed Identity",
            username=f"doomed_{uuid.uuid4().hex[:8]}",
            password_hash=hash_password("secret123"),
            location="US",
            age=30,
            status=IdentityStatus.fresh,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)
        identity_id = identity.id

    async def fake_run(**_):
        raise RuntimeError("signup blew up mid-pipeline")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", return_value=_fake_proxy()), \
         patch("app.services.proxy_service.import_proxies_from_free_list", return_value={"imported": 0, "skipped": 0}):
        await identity_service.start_email_pipeline_for_identity(
            identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
        )

    async with AsyncSessionLocal() as db:
        assert await db.get(Identity, identity_id) is None

    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert status["display_name"] == "Doomed Identity"
    assert "signup blew up mid-pipeline" in status["error"]


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
         patch("app.services.identity_service._select_and_test_proxy", return_value=_fake_proxy()), \
         patch("app.services.proxy_service.import_proxies_from_free_list", return_value={"imported": 0, "skipped": 0}):
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
        proxy = await db.get(Proxy, proxy_id)
        assert proxy is not None  # kept, not deleted - see the Proxy model's consumed_at
        assert proxy.consumed_at is not None


@pytest.mark.asyncio
async def test_select_and_test_proxy_uses_assigned_proxy_without_retesting_or_scraping():
    """The Identities page's generation flow now live-tests candidates itself
    (via the same /test endpoint) and assigns one to the identity before it's
    even created - _select_and_test_proxy should just use that directly, with
    no re-test (check_proxy_health) and no pool-refresh scrape
    (import_proxies_from_free_list), since re-doing work already done moments
    ago would only slow pipeline start down for nothing."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    identity_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.9", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="test-assigned", assigned_bot_id=identity_id,
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    logged = []
    with patch("app.services.identity_service.check_proxy_health") as mock_check, \
         patch("app.services.identity_service.proxy_service.import_proxies_from_free_list") as mock_import:
        async with AsyncSessionLocal() as db:
            result = await identity_service._select_and_test_proxy(db, identity_id, log=logged.append)

    assert result is not None
    assert result.id == proxy_id
    mock_check.assert_not_called()
    mock_import.assert_not_called()
    assert any("no re-test or pool refresh needed" in m for m in logged)

    async with AsyncSessionLocal() as db:
        proxy = await db.get(Proxy, proxy_id)
        assert proxy is not None  # kept, not deleted - see the Proxy model's consumed_at
        assert proxy.consumed_at is not None


@pytest.mark.asyncio
async def test_select_and_test_proxy_uses_an_assigned_datacenter_proxy_rather_than_leaking_it():
    """The assigned fast path must not re-apply the residential/mobile
    preference. The pipeline scheduler only escalates to a datacenter proxy
    after exhausting the alternatives, and it reserves that proxy for the
    identity before creating it - so refusing it here would both discard a
    proxy just proven alive and leak the reservation: the row would stay
    assigned to this identity forever while the pipeline went off to scrape,
    with nothing left to hand it back."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    identity_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.41", port=3128, protocol=ProxyProtocol.http, type=ProxyType.datacenter,
            country="UN", provider="test-assigned-datacenter", assigned_bot_id=identity_id,
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    with patch("app.services.identity_service.check_proxy_health") as mock_check, \
         patch("app.services.identity_service.proxy_service.import_proxies_from_free_list") as mock_import:
        async with AsyncSessionLocal() as db:
            result = await identity_service._select_and_test_proxy(db, identity_id, log=lambda _m: None)

    assert result is not None
    assert result.id == proxy_id
    mock_check.assert_not_called()
    mock_import.assert_not_called()

    async with AsyncSessionLocal() as db:
        assert (await db.get(Proxy, proxy_id)).consumed_at is not None


@pytest.mark.asyncio
async def test_consumed_proxy_never_becomes_selectable_again_even_after_identity_deleted():
    """Regression test for exactly the failure mode reported live (Tuta
    blocking an IP for suspected abuse): a proxy must never be handed to a
    second pipeline once it's been used once, no matter what happens to the
    identity that used it. Covers two ways that could otherwise leak a
    proxy back into the pool - deleting the identity that consumed it, and a
    later free-proxy-list scrape turning up the exact same host:port again."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    identity_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        consumed = Proxy(
            host="198.51.100.44", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="consumed-test", assigned_bot_id=identity_id,
        )
        db.add(consumed)
        await db.commit()
        await db.refresh(consumed)
        proxy_id = consumed.id

    with patch("app.services.identity_service.check_proxy_health"), \
         patch("app.services.identity_service.proxy_service.import_proxies_from_free_list"):
        async with AsyncSessionLocal() as db:
            used = await identity_service._select_and_test_proxy(db, identity_id)
    assert used is not None and used.id == proxy_id

    # Deleting the identity that consumed it must not release it back to the
    # pool - unlike an unconsumed assigned proxy, which delete_identity does
    # release (see test_failed_pipeline_deletes_the_identity's sibling
    # coverage of the un-consumed case via _delete_failed_identity).
    async with AsyncSessionLocal() as db:
        from app.models.identity import Identity, IdentityStatus
        from app.auth.utils import hash_password
        identity = Identity(
            id=identity_id, display_name="Consumed Proxy Owner", username=f"cpo_{uuid.uuid4().hex[:8]}",
            password_hash=hash_password("secret123"), location="US", age=30, status=IdentityStatus.fresh,
        )
        db.add(identity)
        await db.commit()
        await identity_service.delete_identity(db, identity_id)
        await db.commit()

    async with AsyncSessionLocal() as db:
        proxy = await db.get(Proxy, proxy_id)
        assert proxy is not None
        # Unlike an unconsumed assigned proxy (which delete_identity does
        # release), a consumed one is left exactly as it was - assigned_bot_id
        # stays as a historical record of who used it, and is deliberately
        # NOT cleared, since the only thing that actually matters for
        # exclusivity is that consumed_at stays set forever.
        assert proxy.assigned_bot_id == identity_id
        assert proxy.consumed_at is not None

    # A fresh scrape that happens to turn up the exact same host:port must
    # not re-add it as if it were a new, available candidate.
    from app.services import proxy_service as real_proxy_service
    with patch(
        "app.services.proxy_service.fetch_proxies_from_free_proxy_list",
        return_value=[{
            "host": "198.51.100.44", "port": 8080, "protocol": "http",
            "type": "residential", "country": "US", "provider": "free-proxy-list",
        }],
    ), patch("app.services.proxy_service.fetch_proxies_from_proxyscrape", return_value=[]):
        async with AsyncSessionLocal() as db:
            result = await real_proxy_service.import_proxies_from_free_list(db)
    assert result["imported"] == 0
    assert result["skipped"] == 1

    async with AsyncSessionLocal() as db:
        assert await db.get(Proxy, proxy_id) is not None  # still exactly one row for this host:port


@pytest.mark.asyncio
async def test_select_and_test_proxy_keeps_retrying_across_rounds_until_one_is_alive():
    """A proxy is mandatory - _select_and_test_proxy must not give up after a
    single test pass just because everything in the pool right now is dead. It
    makes progress by importing NEW candidates, never by re-testing ones already
    found dead: a failed check flags the proxy, and flagged proxies are filtered
    out of later rounds entirely (which is what keeps "each proxy tested once"
    true across rounds, not just within one).

    Every other untested candidate is marked consumed first so this runs against
    exactly two known rows in the shared, session-accumulated DB."""
    from datetime import datetime, timezone
    from sqlalchemy import update as sa_update
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Proxy)
            .where(Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
            .values(consumed_at=datetime.now(timezone.utc))
        )
        await db.commit()

    identity_id = uuid.uuid4()
    dead_host, live_host = "203.0.113.50", "203.0.113.52"
    async with AsyncSessionLocal() as db:
        db.add(Proxy(
            host=dead_host, port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="retry-test",
        ))
        await db.commit()

    health_calls = []

    def fake_check_health(host, port, protocol, **_kwargs):
        health_calls.append(host)
        return host == live_host

    async def fake_import(db):
        """Stands in for the scrape a later round does: brings in one new,
        working candidate."""
        db.add(Proxy(
            host=live_host, port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="retry-test-round-2",
        ))
        await db.commit()
        return {"imported": 1, "skipped": 0}

    with patch("app.services.identity_service.MAX_PROXY_SCRAPE_ROUNDS", 5), \
         patch("app.services.identity_service.PROXY_SCRAPE_ROUND_DELAY_S", 0), \
         patch("app.services.identity_service.check_proxy_health", side_effect=fake_check_health), \
         patch(
             "app.services.identity_service.proxy_service.import_proxies_from_free_list",
             side_effect=fake_import,
         ) as mock_import:
        async with AsyncSessionLocal() as db:
            result = await identity_service._select_and_test_proxy(db, identity_id)

    assert result is not None
    assert result.host == live_host
    # Round 1 tested the dead one; round 2 tested only the newly imported one.
    # The dead proxy must NOT appear twice - once flagged, it's out until the
    # next import replaces it.
    assert health_calls == [dead_host, live_host]
    # Round 1 deliberately doesn't scrape - it tests the pool exactly as the
    # refresher worker left it, which is normally fresher than a scrape here
    # would be. Only round 2 onwards scrapes, so reaching round 2 means exactly
    # one scrape happened.
    assert mock_import.call_count == 1


@pytest.mark.asyncio
async def test_select_and_test_proxy_gives_up_after_round_budget_exhausted():
    """If nothing ever comes back alive, this must still terminate (not hang
    forever) once the round budget runs out, returning None so the caller can
    fail the pipeline cleanly rather than running it unproxied. Same
    isolation concern as the sibling test above - check_proxy_health is
    patched to always return False regardless of which candidate is passed,
    so pre-existing rows in this shared DB don't affect the outcome, only
    how many total calls happen (which this test doesn't assert on)."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    identity_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.51", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="retry-test-2",
        )
        db.add(proxy)
        await db.commit()

    with patch("app.services.identity_service.MAX_PROXY_SCRAPE_ROUNDS", 3), \
         patch("app.services.identity_service.PROXY_SCRAPE_ROUND_DELAY_S", 0), \
         patch("app.services.identity_service.check_proxy_health", return_value=False), \
         patch(
             "app.services.identity_service.proxy_service.import_proxies_from_free_list",
             return_value={"imported": 0, "skipped": 0},
         ) as mock_import:
        async with AsyncSessionLocal() as db:
            result = await identity_service._select_and_test_proxy(db, identity_id)

    assert result is None
    # Every round in the budget was tried, then it stopped. One fewer scrape
    # than rounds: round 1 works with the pool as-is (see the sibling test).
    assert mock_import.call_count == 2


@pytest.mark.asyncio
async def test_create_identity_with_proxy_id_claims_it_atomically():
    """Regression test for a real race: the frontend used to create the
    identity first, then send a *separate* follow-up PATCH to assign the
    proxy - but the background pipeline task starts as soon as the create
    request's response is sent, and could reach its own proxy-selection step
    before that second request even landed, missing the already-tested
    proxy entirely. IdentityCreate.proxy_id closes that gap by claiming the
    proxy in the same request/transaction that creates the identity, so it's
    guaranteed committed - and visible to a completely separate DB session,
    exactly like the background task uses - the moment this call returns."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.schemas.identity import IdentityCreate

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.90", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="atomic-claim-test",
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    data = IdentityCreate(
        display_name="Atomic Claim Test", username=f"atomic_{uuid.uuid4().hex[:8]}",
        location="US", age=30, password="secret123", proxy_id=proxy_id,
    )
    async with AsyncSessionLocal() as db:
        identity = await identity_service.create_identity(db, data)
        identity_id = identity.id

    # A completely separate session - same as the one the background
    # pipeline task actually uses - must see the claim as already committed.
    async with AsyncSessionLocal() as fresh_db:
        claimed = await fresh_db.get(Proxy, proxy_id)
        assert claimed.assigned_bot_id == identity_id
        assert claimed.consumed_at is None  # reserved, not yet consumed - the pipeline does that


@pytest.mark.asyncio
async def test_test_proxy_claim_for_prevents_two_identities_winning_the_same_proxy():
    """Regression test for the race reported live: testing a proxy alone
    used to leave it fully unclaimed until a *separate*, later request
    reserved it - and in between, a different concurrent claim (another
    identity's own generation flow, or a different pipeline's free-pool
    search) could grab the exact same proxy first, despite this one having
    "found" it moments earlier. proxy_service.test_proxy's claim_for closes
    this by claiming atomically in the same call that confirms health -
    fires two concurrent test-and-claim calls for two different identity ids
    on the same proxy and asserts exactly one of them actually wins it."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType
    from app.services import proxy_service

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.60", port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
            country="US", provider="claim-for-race-test",
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    id_a, id_b = uuid.uuid4(), uuid.uuid4()
    with patch("app.services.proxy_service.check_proxy_health", return_value=True):
        async with AsyncSessionLocal() as db_a, AsyncSessionLocal() as db_b:
            result_a, result_b = await asyncio.gather(
                proxy_service.test_proxy(db_a, proxy_id, claim_for=id_a),
                proxy_service.test_proxy(db_b, proxy_id, claim_for=id_b),
            )

    # Both calls refresh from the DB after attempting their claim, so both
    # results reflect the same actual final row - whichever claim_for really
    # won, not necessarily each caller's own. Exactly one identity ever ends
    # up with this proxy.
    assert result_a.assigned_bot_id == result_b.assigned_bot_id
    assert result_a.assigned_bot_id in (id_a, id_b)

    async with AsyncSessionLocal() as db:
        final = await db.get(Proxy, proxy_id)
        assert final.assigned_bot_id in (id_a, id_b)


@pytest.mark.asyncio
async def test_session_timeout_closes_a_session_that_never_resolves():
    """Every per-step wait inside the actual Tuta pipeline is deliberately
    unbounded (see tuta.py's VERIFY_TIMEOUT_MS), so a session whose
    underlying connection just hangs - never errors, never resolves - needs
    an outer backstop or it sits "running" forever, holding a browser
    instance in memory. Simulates exactly that: a fake provider.run() that
    never returns, with SESSION_TIMEOUT_S patched down so the test doesn't
    actually wait 5 minutes to prove it."""
    identity_id = uuid.uuid4()
    reached_run = asyncio.Event()

    async def fake_run(**_):
        reached_run.set()
        await asyncio.sleep(3600)  # never actually resolves within the test

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", return_value=_fake_proxy()), \
         patch("app.services.proxy_service.import_proxies_from_free_list", return_value={"imported": 0, "skipped": 0}), \
         patch("app.services.identity_service.SESSION_TIMEOUT_S", 0.2):
        await asyncio.wait_for(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            ),
            timeout=5,  # sanity bound on the test itself - should finish well under this
        )

    assert reached_run.is_set()
    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert "session exceeded" in status["error"]


async def _make_proxies(hosts: list[str], provider: str):
    """Real Proxy rows, returned as ids - retire_proxy updates by id, so
    asserting on retirement needs actual rows rather than stand-ins."""
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ids = []
    async with AsyncSessionLocal() as db:
        for host in hosts:
            proxy = Proxy(
                host=host, port=8080, protocol=ProxyProtocol.http, type=ProxyType.residential,
                country="US", provider=provider,
            )
            db.add(proxy)
            await db.flush()
            ids.append(proxy.id)
        await db.commit()
    return ids


def _hand_out_in_order(proxy_ids: list):
    """Stands in for _select_and_test_proxy, giving each attempt the next proxy
    in the list so a test can say exactly which proxy failed when."""
    from app.database import AsyncSessionLocal
    from app.models.proxy import Proxy

    handed: list = []

    async def fake_select(db, identity_id, log=lambda _m: None):
        async with AsyncSessionLocal() as session:
            proxy = await session.get(Proxy, proxy_ids[len(handed)])
        handed.append(proxy.id)
        return proxy

    return fake_select, handed


@pytest.mark.asyncio
async def test_pipeline_retires_a_failed_proxy_and_retries_the_whole_run_on_another():
    """The reported failure mode: a proxy passes its health check, then Chrome
    reports net::ERR_TIMED_OUT the moment the browser actually navigates through
    it. That says nothing about whether the signup would work, so the run
    retires that proxy and starts over on a fresh one instead of failing.

    Also covers the boundary: once a failure is NOT the proxy's fault, retrying
    stops immediately (and that proxy is not flagged - it did its job)."""
    from app.database import AsyncSessionLocal
    from app.models.proxy import Proxy

    identity_id = uuid.uuid4()
    proxy_ids = await _make_proxies(["203.0.113.70", "203.0.113.71", "203.0.113.72"], "flag-test")
    fake_select, handed = _hand_out_in_order(proxy_ids)

    attempts = []

    async def fake_run(**_):
        attempts.append(1)
        if len(attempts) <= 2:
            # Exactly what Playwright surfaces for a dead proxy.
            raise RuntimeError('Page.goto: net::ERR_TIMED_OUT at https://tuta.com/cs')
        raise RuntimeError("step_submit_account: signup button never became visible")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select):
        await identity_service.start_email_pipeline_for_identity(
            identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
        )

    assert len(attempts) == 3, "each proxy-level failure should retry on a new proxy"
    assert handed == proxy_ids, "each attempt must get a different proxy"

    async with AsyncSessionLocal() as db:
        first, second, third = [await db.get(Proxy, pid) for pid in proxy_ids]
        for row in (first, second):
            # Flagged as not working, which is what keeps any other identity
            # from picking it up...
            assert row.is_healthy is False
            assert row.assigned_bot_id is None
            # ...but NOT blacklisted. consumed_at means "an account was
            # registered through this IP" and is permanent; these never got a
            # byte through, so the next import is free to bring them back.
            assert row.consumed_at is None
        # The third failed for a reason that wasn't its fault, so it's left
        # completely untouched - not flagged. (In a real run it would also still
        # be consumed by the attempt that used it; _select_and_test_proxy, which
        # is what consumes, is stubbed out here.)
        assert third.is_healthy is True

    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert "signup button never became visible" in status["error"]


@pytest.mark.asyncio
async def test_a_flagged_proxy_is_hidden_from_searches_but_returns_on_the_next_import():
    """The exact contract asked for: a proxy that failed in use is out of reach
    of every other identity, yet is not blacklisted - the refresher's next cycle
    drops it with the rest of the stale pool and re-imports it from the source as
    a fresh, healthy candidate."""
    from app.database import AsyncSessionLocal
    from app.models.proxy import Proxy
    from app.services import proxy_service as real_proxy_service

    host = "203.0.113.150"
    (proxy_id,) = await _make_proxies([host], "flag-then-reimport-test")

    await identity_service.flag_proxy_not_working(proxy_id, "test")

    # Invisible to every candidate search while flagged.
    async with AsyncSessionLocal() as db:
        candidates = await identity_service.list_free_proxy_candidates(db, allow_datacenter=True)
        assert proxy_id not in {c.id for c in candidates}
        # Not blacklisted: still a plain free row, just a dead one.
        row = await db.get(Proxy, proxy_id)
        assert row.consumed_at is None and row.is_healthy is False

    # The refresher replaces the free pool; the source still lists this address.
    scraped = [{
        "host": host, "port": 8080, "protocol": "http",
        "type": "residential", "country": "US", "provider": "free-proxy-list",
    }]
    with patch("app.services.proxy_service.fetch_all_free_proxies", return_value=scraped):
        async with AsyncSessionLocal() as db:
            result = await real_proxy_service.replace_free_proxy_pool(db)

    assert result.get("error") is None
    assert result["imported"] >= 1, "a flagged proxy must be re-importable, not permanently skipped"

    async with AsyncSessionLocal() as db:
        # Back as a brand new row (the old one was dropped with the stale pool),
        # healthy, and selectable again.
        candidates = await identity_service.list_free_proxy_candidates(db, allow_datacenter=True)
        assert host in {c.host for c in candidates}
        assert await db.get(Proxy, proxy_id) is None


@pytest.mark.asyncio
async def test_pipeline_gives_up_after_its_proxy_attempt_budget():
    """Unbounded retrying would pin a scheduler slot and a Chromium instance
    forever against a pool where nothing works, so the run stops after
    MAX_PROXY_ATTEMPTS_PER_RUN - having flagged every proxy it tried."""
    from app.database import AsyncSessionLocal
    from app.models.proxy import Proxy

    identity_id = uuid.uuid4()
    proxy_ids = await _make_proxies(["203.0.113.80", "203.0.113.81", "203.0.113.82"], "budget-test")
    fake_select, _handed = _hand_out_in_order(proxy_ids)

    attempts = []

    async def fake_run(**_):
        attempts.append(1)
        raise RuntimeError('Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://tuta.com/cs')

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.MAX_PROXY_ATTEMPTS_PER_RUN", 3):
        await identity_service.start_email_pipeline_for_identity(
            identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
        )

    assert len(attempts) == 3
    async with AsyncSessionLocal() as db:
        for pid in proxy_ids:
            row = await db.get(Proxy, pid)
            assert row.is_healthy is False
            assert row.consumed_at is None  # flagged, not blacklisted

    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert "gave up after 3 proxies" in status["error"]
    assert "ERR_TUNNEL_CONNECTION_FAILED" in status["error"]


@pytest.mark.asyncio
async def test_hung_sessions_get_a_much_smaller_retry_budget_than_fast_failures():
    """A Chrome network error comes back in seconds, so trying 25 proxies costs
    little. A hung session costs minutes each, so retrying it 25 times would
    hold a slot for hours - it gets its own small allowance."""
    identity_id = uuid.uuid4()
    proxy_ids = await _make_proxies(["203.0.113.90", "203.0.113.91", "203.0.113.92"], "hang-test")
    fake_select, _handed = _hand_out_in_order(proxy_ids)

    attempts = []

    async def fake_run(**_):
        attempts.append(1)
        await asyncio.sleep(3600)  # hangs rather than erroring, like a half-dead proxy

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.STEP_STALL_TIMEOUT_S", 0.05), \
         patch("app.services.identity_service.MAX_HUNG_SESSIONS_PER_RUN", 2), \
         patch("app.services.identity_service.MAX_PROXY_ATTEMPTS_PER_RUN", 25):
        await asyncio.wait_for(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            ),
            timeout=10,
        )

    assert len(attempts) == 2, "hung sessions must not consume the full proxy budget"
    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert "session(s) hung" in status["error"]


@pytest.mark.asyncio
async def test_a_step_that_stops_advancing_terminates_the_session():
    """A run that never changes step is killed after STEP_STALL_TIMEOUT_S rather
    than sitting there holding a browser. The provider here reaches its first
    step and then hangs forever - exactly what a page that will never resolve
    looks like from out here."""
    identity_id = uuid.uuid4()
    (proxy_id,) = await _make_proxies(["203.0.113.100"], "stall-test")
    fake_select, _handed = _hand_out_in_order([proxy_id])

    cancelled = asyncio.Event()

    async def fake_run(on_step=None, **_):
        on_step(0, SimpleNamespace(name="open_homepage", manual=False))
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            # The provider's own `finally: browser.close()` runs at this point -
            # the guard has to await the cancellation for that to happen.
            cancelled.set()
            raise

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.STEP_STALL_TIMEOUT_S", 0.2), \
         patch("app.services.identity_service.SESSION_TIMEOUT_S", 30), \
         patch("app.services.identity_service.MAX_HUNG_SESSIONS_PER_RUN", 1):
        await asyncio.wait_for(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            ),
            timeout=10,
        )

    assert cancelled.is_set(), "the stalled run must be cancelled, not abandoned"
    status = identity_service.get_pipeline_status(identity_id)
    assert status["status"] == "failed"
    assert "no pipeline step change" in status["error"]


@pytest.mark.asyncio
async def test_a_run_that_keeps_advancing_is_never_killed_for_being_slow():
    """The guard watches for progress, not duration. A run whose steps each take
    most of the stall window but keep coming must be left alone - the whole
    reason every internal wait is unbounded is that a slow page shouldn't fail a
    step."""
    identity_id = uuid.uuid4()
    (proxy_id,) = await _make_proxies(["203.0.113.101"], "slow-but-moving-test")
    fake_select, _handed = _hand_out_in_order([proxy_id])

    async def fake_run(on_step=None, **_):
        # Six steps, each taking most of the stall allowance: far past it in
        # total, but never stalled.
        for index in range(6):
            on_step(index, SimpleNamespace(name=f"step_{index}", manual=False))
            await asyncio.sleep(0.15)
        return SimpleNamespace(username="slowbutsteady123456", password="Sunshine1234!")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.STEP_STALL_TIMEOUT_S", 0.25), \
         patch("app.services.identity_service.SESSION_TIMEOUT_S", 30):
        await asyncio.wait_for(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            ),
            timeout=10,
        )

    # These tests never create an Identity row, so attaching the mailbox
    # afterwards fails on its own - which is fine. What matters is that the run
    # was allowed to reach that point at all, i.e. the guard did not kill it.
    status = identity_service.get_pipeline_status(identity_id)
    assert "no pipeline step change" not in (status.get("error") or ""), status["error"]
    assert "session exceeded" not in (status.get("error") or ""), status["error"]


@pytest.mark.asyncio
async def test_a_manual_step_is_exempt_from_the_stall_timeout():
    """A step waiting on a person is stalled by design. Putting a three-minute
    stopwatch on it would just be a race against how fast someone notices the
    dashboard."""
    identity_id = uuid.uuid4()
    (proxy_id,) = await _make_proxies(["203.0.113.102"], "manual-step-test")
    fake_select, _handed = _hand_out_in_order([proxy_id])

    async def fake_run(on_step=None, **_):
        on_step(0, SimpleNamespace(name="manual_captcha", manual=True))
        # Far longer than the stall allowance - and legitimately so.
        await asyncio.sleep(0.6)
        on_step(1, SimpleNamespace(name="after_captcha", manual=False))
        return SimpleNamespace(username="waitedforahuman12345", password="Sunshine1234!")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.STEP_STALL_TIMEOUT_S", 0.15), \
         patch("app.services.identity_service.SESSION_TIMEOUT_S", 30):
        await asyncio.wait_for(
            identity_service.start_email_pipeline_for_identity(
                identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
            ),
            timeout=10,
        )

    # These tests never create an Identity row, so attaching the mailbox
    # afterwards fails on its own - which is fine. What matters is that the run
    # was allowed to reach that point at all, i.e. the guard did not kill it.
    status = identity_service.get_pipeline_status(identity_id)
    assert "no pipeline step change" not in (status.get("error") or ""), status["error"]
    assert "session exceeded" not in (status.get("error") or ""), status["error"]


@pytest.mark.asyncio
async def test_ip_blocked_banner_counts_as_a_proxy_failure():
    """Tuta's "this IP is blocked for suspected abuse" banner means the proxy's
    address is burned for this site. The proxy works fine at the network level,
    so no Chrome error appears - but a different proxy is still the only fix,
    and the same one must never be offered again."""
    from app.database import AsyncSessionLocal
    from app.models.proxy import Proxy

    identity_id = uuid.uuid4()
    proxy_ids = await _make_proxies(["203.0.113.95", "203.0.113.96"], "ipblock-test")
    fake_select, _handed = _hand_out_in_order(proxy_ids)

    attempts = []

    async def fake_run(**_):
        attempts.append(1)
        # Exactly what tuta.py's _raise_if_ip_blocked raises.
        raise RuntimeError("ip_blocked: Tuta blocked this IP for suspected abuse - closing the session")

    fake_provider = ProviderPipeline(run=fake_run, describe=lambda: [])

    with patch("app.services.identity_service.get_provider_pipeline", return_value=fake_provider), \
         patch("app.services.identity_service._select_and_test_proxy", side_effect=fake_select), \
         patch("app.services.identity_service.MAX_PROXY_ATTEMPTS_PER_RUN", 2):
        await identity_service.start_email_pipeline_for_identity(
            identity_id, "fake-provider", "example.com", uuid.uuid4(), "classic"
        )

    assert len(attempts) == 2, "an IP-blocked proxy should be swapped, not retried on"
    async with AsyncSessionLocal() as db:
        for pid in proxy_ids:
            row = await db.get(Proxy, pid)
            assert row.is_healthy is False
            # No account was registered - Tuta refused before that - so this is
            # a flag, not a blacklist entry.
            assert row.consumed_at is None


@pytest.mark.asyncio
async def test_select_and_test_proxy_falls_back_to_datacenter_as_last_resort():
    """Residential/mobile is strongly preferred (more likely to work cleanly
    against a real site's anti-abuse heuristics), but a proxy is mandatory -
    refusing to run at all when only a datacenter proxy exists is worse than
    using one. Only a datacenter proxy is available here; every round before
    the last one must skip it (so it must NOT be picked early), and only the
    final, last-resort round may pick it up.

    check_proxy_health is patched to always succeed, so - same isolation
    concern as the round-retry tests above - every other untested
    residential/mobile candidate in this shared, session-accumulated DB is
    marked consumed first, or one of *those* would win on round 1 instead of
    this test ever reaching the last-resort round at all."""
    from datetime import datetime, timezone
    from sqlalchemy import update as sa_update
    from app.database import AsyncSessionLocal, Base, engine
    from app.models.proxy import Proxy, ProxyProtocol, ProxyType

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Proxy)
            .where(Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
            .values(consumed_at=datetime.now(timezone.utc))
        )
        await db.commit()

    identity_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        proxy = Proxy(
            host="203.0.113.70", port=8080, protocol=ProxyProtocol.http, type=ProxyType.datacenter,
            country="US", provider="last-resort-test",
        )
        db.add(proxy)
        await db.commit()
        await db.refresh(proxy)
        proxy_id = proxy.id

    with patch("app.services.identity_service.MAX_PROXY_SCRAPE_ROUNDS", 3), \
         patch("app.services.identity_service.PROXY_SCRAPE_ROUND_DELAY_S", 0), \
         patch("app.services.identity_service.check_proxy_health", return_value=True), \
         patch(
             "app.services.identity_service.proxy_service.import_proxies_from_free_list",
             return_value={"imported": 0, "skipped": 0},
         ):
        async with AsyncSessionLocal() as db:
            result = await identity_service._select_and_test_proxy(db, identity_id)

    assert result is not None
    assert result.id == proxy_id
    assert result.type == ProxyType.datacenter
