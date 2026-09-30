"""Covers the two background workers: the proxy refresher (keeps the pool
fresh) and the pipeline scheduler (keeps N signup pipelines in flight).

Nothing here touches the network or launches a browser - the scrape, the health
check and the pipeline itself are all patched out. What's under test is the
orchestration: that slots stay occupied, that a finished pipeline is
immediately replaced, that a candidate proxy is never handed to two slots, and
that a reservation made for an identity that never got created is handed back.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.email_platform import EmailPlatformType
from app.models.proxy import Proxy, ProxyProtocol, ProxyType
from app.services import identity_service, proxy_service
from app.workers import pipeline_scheduler as scheduler_mod
from app.workers.base import LoopWorker
from app.workers.pipeline_scheduler import PipelineScheduler, _CandidateQueue, _Job


class _FakeSession:
    """Stand-in for AsyncSessionLocal() in the worker modules, which reach for
    their own session rather than a request-scoped one. Everything that would
    actually touch it is patched out in these tests."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def commit(self):
        return None


async def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached within the timeout")
        await asyncio.sleep(0.01)


def _candidate(n: int) -> identity_service.ProxyCandidate:
    return identity_service.ProxyCandidate(
        id=uuid4(), host=f"10.0.0.{n}", port=8080, protocol="http",
        type="residential", username=None, password=None,
    )


def _platform() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), name="tuta", domain="tuta.com", type=EmailPlatformType.temporary,
    )


def _fast_scheduler(monkeypatch, concurrency: int = 7, continuous: bool = True) -> PipelineScheduler:
    """A scheduler wired for tests: platform resolution stubbed out, and by
    default in continuous mode so it invents its own work instead of each test
    having to queue jobs just to get slots moving."""
    scheduler = PipelineScheduler(concurrency=concurrency)
    # The supervisor's real cadence is seconds; there's nothing to wait for
    # here, so don't make the test sit through it.
    scheduler.interval_s = 0.01
    scheduler.continuous = continuous
    scheduler.email_platform_id = uuid4()
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", _FakeSession)
    monkeypatch.setattr(scheduler, "_resolve_platform", AsyncMock(return_value=_platform()))
    # Stopping a scheduler cancels its slots, and each one then tries to hand
    # its proxy reservation back - which would reach the real database. Tests
    # that care about the release assert on their own stub instead.
    monkeypatch.setattr(identity_service, "release_proxy_reservations", AsyncMock(return_value=0))
    return scheduler


# --- the shared candidate queue -----------------------------------------

@pytest.mark.asyncio
async def test_candidate_queue_never_hands_the_same_proxy_to_two_slots(monkeypatch):
    """The bug this queue exists to prevent: every slot queries the pool
    itself, gets the same freshest-first ordering back, and then health-checks
    the same top-of-the-list rows - so with seven slots, six of the seven
    searches are pure duplicated work. One shared cursor means each candidate
    is handed to exactly one slot, and the pool is queried once, not once per
    slot."""
    candidates = [_candidate(n) for n in range(100)]
    refill_calls = []

    async def fake_list(db, allow_datacenter=False):
        refill_calls.append(allow_datacenter)
        return list(candidates)

    monkeypatch.setattr(identity_service, "list_free_proxy_candidates", fake_list)
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", _FakeSession)

    queue = _CandidateQueue()
    batches = await asyncio.gather(*(queue.take(20, False) for _ in range(5)))

    handed = [candidate.id for batch in batches for candidate in batch]
    assert len(handed) == 100
    assert len(set(handed)) == 100, "a candidate was handed to more than one taker"
    assert refill_calls == [False], "the pool was queried once per taker instead of once"


@pytest.mark.asyncio
async def test_candidate_queue_returns_nothing_when_the_pool_is_empty(monkeypatch):
    """An empty pool has to surface as "nothing right now" so the slot waits
    for the refresher, rather than as an exception that kills the slot."""
    monkeypatch.setattr(identity_service, "list_free_proxy_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", _FakeSession)

    assert await _CandidateQueue().take(20, False) == []


# --- the scheduler ------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_keeps_target_pipelines_running_and_refills_immediately(monkeypatch):
    """The core requirement: seven pipelines in flight at all times, and the
    moment one finishes an eighth starts - not a drain-then-refill batch."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=7)
    monkeypatch.setattr(scheduler, "_reserve_proxy", AsyncMock(return_value="10.0.0.1:8080 (residential)"))

    async def fake_generate(db, identity_id=None):
        return SimpleNamespace(id=identity_id, username=f"user_{identity_id}")

    monkeypatch.setattr(identity_service, "generate_identity", fake_generate)

    running: set = set()
    gates: dict = {}

    async def fake_pipeline(identity_id, *_args):
        gate = asyncio.Event()
        gates[identity_id] = gate
        running.add(identity_id)
        try:
            await gate.wait()
        finally:
            running.discard(identity_id)

    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", fake_pipeline)

    scheduler.start()
    try:
        await _wait_until(lambda: len(running) == 7)
        first_seven = set(running)
        assert scheduler.status()["active_slots"] == 7

        # Finish exactly one. Its slot must come back up on its own.
        gates[next(iter(first_seven))].set()
        await _wait_until(lambda: len(running) == 7 and running != first_seven)

        assert len(first_seven | running) == 8, "the freed slot was not refilled with a new pipeline"
        assert scheduler.status()["launched"] == 8
    finally:
        for gate in gates.values():
            gate.set()
        await scheduler.stop()

    assert scheduler.status()["active_slots"] == 0
    assert not scheduler.is_running()


@pytest.mark.asyncio
async def test_scheduler_gives_every_identity_its_own_id_and_proxy(monkeypatch):
    """Each slot decides its own identity id up front and reserves a proxy
    against that id - no sharing, and no slot waiting on another's proxy
    search."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=5)

    reserved_for = []

    async def fake_reserve(identity_id):
        reserved_for.append(identity_id)
        return f"10.0.0.{len(reserved_for)}:8080 (residential)"

    monkeypatch.setattr(scheduler, "_reserve_proxy", fake_reserve)

    created = []

    async def fake_generate(db, identity_id=None):
        created.append(identity_id)
        return SimpleNamespace(id=identity_id, username=f"user_{identity_id}")

    monkeypatch.setattr(identity_service, "generate_identity", fake_generate)

    stop = asyncio.Event()

    async def fake_pipeline(identity_id, *_args):
        await stop.wait()

    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", fake_pipeline)

    scheduler.start()
    try:
        await _wait_until(lambda: len(created) == 5)
    finally:
        stop.set()
        await scheduler.stop()

    assert len(set(created)) == 5, "two slots created the identity under the same id"
    # The proxy was reserved for the same id the identity was then created
    # under - that pairing is what stops a pipeline from starting before its
    # own reservation landed.
    assert reserved_for == created


@pytest.mark.asyncio
async def test_slot_releases_its_proxy_when_identity_creation_fails(monkeypatch):
    """The reservation is made before the identity exists, so if creation
    fails there is no identity row for delete_identity to clean up - nothing
    else would ever hand the proxy back and it would sit reserved for an id
    that never existed, invisible to every later search."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=1)
    monkeypatch.setattr(scheduler, "_reserve_proxy", AsyncMock(return_value="10.0.0.1:8080 (residential)"))

    async def exploding_generate(db, identity_id=None):
        raise RuntimeError("database went away")

    monkeypatch.setattr(identity_service, "generate_identity", exploding_generate)

    released = []

    async def fake_release(db, identity_id):
        released.append(identity_id)
        return 1

    monkeypatch.setattr(identity_service, "release_proxy_reservations", fake_release)
    pipeline = AsyncMock()
    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", pipeline)

    platform = _platform()
    await scheduler._run_slot(_Job(platform_id=platform.id), platform)

    assert len(released) == 1
    assert scheduler.status()["failed_to_launch"] == 1
    pipeline.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_refuses_a_platform_with_no_automated_pipeline(monkeypatch):
    """Even an explicitly configured platform is rejected when no signup
    pipeline is registered for its name. Every slot would fail on it instantly
    - but only after reserving and consuming a proxy, so the scheduler would
    quietly burn the whole pool a slot at a time."""
    scheduler = PipelineScheduler(concurrency=1)
    monkeypatch.setattr(scheduler_mod, "AsyncSessionLocal", _FakeSession)

    gmail = SimpleNamespace(id=uuid4(), name="gmail", domain="gmail.com", type=EmailPlatformType.classic)
    tuta = SimpleNamespace(id=uuid4(), name="Tuta", domain="tuta.com", type=EmailPlatformType.temporary)

    monkeypatch.setattr(
        scheduler_mod.email_platform_service, "get_email_platform", AsyncMock(return_value=gmail)
    )
    assert await scheduler._resolve_platform(gmail.id) is None

    monkeypatch.setattr(
        scheduler_mod.email_platform_service, "get_email_platform", AsyncMock(return_value=tuta)
    )
    resolved = await scheduler._resolve_platform(tuta.id)
    # Case-insensitively, as the registry lookup is.
    assert resolved is not None and resolved.name == "Tuta"

    # Continuous mode's own pick skips gmail and takes the one with a pipeline.
    monkeypatch.setattr(
        scheduler_mod.email_platform_service, "get_email_platforms", AsyncMock(return_value=[gmail, tuta])
    )
    assert await scheduler.default_platform_id() == tuta.id


@pytest.mark.asyncio
async def test_queued_job_runs_the_identity_it_was_given_instead_of_generating_one(monkeypatch):
    """The normal path: an identity already exists (it was created by the
    request that queued it, so it shows on the Identities page immediately) and
    the slot must run *that* one - not generate a second identity for the same
    piece of work."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=2, continuous=False)
    monkeypatch.setattr(scheduler, "_reserve_proxy", AsyncMock(return_value="10.0.0.1:8080 (residential)"))
    generate = AsyncMock()
    monkeypatch.setattr(identity_service, "generate_identity", generate)

    ran: list = []
    stop = asyncio.Event()

    async def fake_pipeline(identity_id, *_args):
        ran.append(identity_id)
        await stop.wait()

    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", fake_pipeline)

    wanted = [uuid4(), uuid4()]
    platform_id = uuid4()
    for identity_id in wanted:
        assert scheduler.enqueue(identity_id, platform_id, display_name="X", provider_name="tuta")
    # Queueing starts the worker on its own - nothing else has to.
    assert scheduler.is_running()

    try:
        await _wait_until(lambda: len(ran) == 2)
    finally:
        stop.set()
        await scheduler.stop()

    assert set(ran) == set(wanted)
    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_holds_work_beyond_the_concurrency_cap(monkeypatch):
    """Requesting more than the cap must queue the remainder, not run them -
    "20 identities" is 20 rows and a queue, never 20 browsers."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=3, continuous=False)
    monkeypatch.setattr(scheduler, "_reserve_proxy", AsyncMock(return_value="10.0.0.1:8080 (residential)"))

    running: set = set()
    gates: dict = {}

    async def fake_pipeline(identity_id, *_args):
        gate = asyncio.Event()
        gates[identity_id] = gate
        running.add(identity_id)
        try:
            await gate.wait()
        finally:
            running.discard(identity_id)

    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", fake_pipeline)

    platform_id = uuid4()
    for _ in range(10):
        scheduler.enqueue(uuid4(), platform_id, provider_name="tuta")

    try:
        await _wait_until(lambda: len(running) == 3)
        # Give the supervisor several more ticks - it must not exceed the cap.
        await asyncio.sleep(0.1)
        assert len(running) == 3
        assert scheduler.status()["queued"] == 7

        # One finishes -> exactly one more starts, from the queue.
        gates[next(iter(running))].set()
        await _wait_until(lambda: scheduler.status()["queued"] == 6 and len(running) == 3)
        await asyncio.sleep(0.1)
        assert len(running) == 3
        assert scheduler.status()["queued"] == 6
    finally:
        for gate in gates.values():
            gate.set()
        await scheduler.stop()


@pytest.mark.asyncio
async def test_clear_queue_drops_pending_work_only(monkeypatch):
    scheduler = PipelineScheduler(concurrency=1)
    scheduler.interval_s = 3600  # never tick - nothing should start here
    platform_id = uuid4()
    for _ in range(4):
        scheduler.enqueue(uuid4(), platform_id, provider_name="tuta")
    try:
        assert scheduler.status()["queued"] == 4
        assert scheduler.clear_queue() == 4
        assert scheduler.status()["queued"] == 0
    finally:
        await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_drops_jobs_whose_platform_has_no_pipeline(monkeypatch):
    """A job that can't run is dropped, not started and not retried forever. If
    it started, it would reserve and consume a proxy before failing - so a queue
    full of these would quietly burn the pool one job at a time."""
    scheduler = _fast_scheduler(monkeypatch, concurrency=7, continuous=False)
    monkeypatch.setattr(scheduler, "_resolve_platform", AsyncMock(return_value=None))
    pipeline = AsyncMock()
    monkeypatch.setattr(identity_service, "start_email_pipeline_for_identity", pipeline)

    platform_id = uuid4()
    for _ in range(3):
        scheduler.enqueue(uuid4(), platform_id, provider_name="gmail")
    try:
        await scheduler.run_once()
    finally:
        await scheduler.stop()

    assert scheduler.status()["active_slots"] == 0
    assert scheduler.status()["queued"] == 0
    assert scheduler.status()["failed_to_launch"] == 3
    pipeline.assert_not_awaited()


# --- the loop base ------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_keeps_looping_after_a_failing_cycle():
    """A transient failure (a scrape timing out, one bad pipeline) must not
    take the worker down - the invariants these loops maintain are supposed to
    keep holding without anyone watching."""

    class _Flaky(LoopWorker):
        name = "flaky"
        interval_s = 0.01

        def __init__(self):
            super().__init__()
            self.runs = 0

        async def run_once(self):
            self.runs += 1
            if self.runs == 1:
                raise RuntimeError("transient")

    worker = _Flaky()
    assert worker.start() is True
    assert worker.start() is False, "a second start should be a no-op, not a second loop"
    try:
        await _wait_until(lambda: worker.runs >= 3)
    finally:
        await worker.stop()

    assert not worker.is_running()
    assert worker.status()["last_error"] is None, "a later successful cycle should clear the error"


# --- the refresher ------------------------------------------------------

@pytest.mark.asyncio
async def test_replace_free_proxy_pool_keeps_reserved_and_consumed_rows(db_session, monkeypatch):
    """"Replace the list" means replace the *free* part of it. A reserved row
    belongs to an in-flight pipeline and a consumed row is a permanent record
    that an IP has been used - dropping either would either break a running
    pipeline or let a used IP come back into circulation on the next scrape."""
    reserved_for = uuid4()
    was_free = Proxy(host="198.51.100.1", port=8080, protocol=ProxyProtocol.http,
                     type=ProxyType.datacenter, country="UN", provider="proxyscrape")
    reserved = Proxy(host="198.51.100.2", port=8080, protocol=ProxyProtocol.http,
                     type=ProxyType.residential, country="US", provider="free-proxy-list",
                     assigned_bot_id=reserved_for)
    consumed = Proxy(host="198.51.100.3", port=8080, protocol=ProxyProtocol.http,
                     type=ProxyType.residential, country="US", provider="free-proxy-list",
                     assigned_bot_id=uuid4(), consumed_at=datetime.now(timezone.utc))
    db_session.add_all([was_free, reserved, consumed])
    await db_session.commit()
    free_row_id_before = was_free.id

    scraped = [
        # Previously free - dropped and re-imported as a fresh row.
        {"host": "198.51.100.1", "port": 8080, "protocol": "http", "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
        # Already consumed - must NOT come back.
        {"host": "198.51.100.3", "port": 8080, "protocol": "http", "type": "residential", "country": "US", "provider": "free-proxy-list"},
        # Brand new.
        {"host": "198.51.100.9", "port": 3128, "protocol": "http", "type": "datacenter", "country": "UN", "provider": "proxyscrape"},
    ]
    monkeypatch.setattr(proxy_service, "fetch_all_free_proxies", AsyncMock(return_value=scraped))

    result = await proxy_service.replace_free_proxy_pool(db_session)
    assert result.get("error") is None

    rows = (await db_session.execute(
        select(Proxy).where(Proxy.host.in_(["198.51.100.1", "198.51.100.2", "198.51.100.3", "198.51.100.9"]))
    )).scalars().all()
    by_host = {}
    for row in rows:
        by_host.setdefault(row.host, []).append(row)

    assert by_host["198.51.100.2"][0].assigned_bot_id == reserved_for, "a reserved proxy was dropped"
    assert len(by_host["198.51.100.3"]) == 1, "a consumed proxy was re-imported as a duplicate"
    assert by_host["198.51.100.3"][0].consumed_at is not None
    assert len(by_host["198.51.100.1"]) == 1
    assert by_host["198.51.100.1"][0].id != free_row_id_before, "the free row was not actually replaced"
    assert "198.51.100.9" in by_host


@pytest.mark.asyncio
async def test_replace_free_proxy_pool_keeps_the_old_list_when_every_source_fails(db_session, monkeypatch):
    """Both sources down must not leave the scheduler with an empty pool -
    a stale list is still better than no list."""
    survivor = Proxy(host="198.51.100.77", port=8080, protocol=ProxyProtocol.http,
                     type=ProxyType.datacenter, country="UN", provider="proxyscrape")
    db_session.add(survivor)
    await db_session.commit()

    monkeypatch.setattr(proxy_service, "fetch_all_free_proxies", AsyncMock(return_value=[]))
    result = await proxy_service.replace_free_proxy_pool(db_session)

    assert result["error"]
    assert result["removed"] == 0
    still_there = (await db_session.execute(
        select(Proxy).where(Proxy.host == "198.51.100.77")
    )).scalar_one_or_none()
    assert still_there is not None


# --- generate_identity's explicit id ------------------------------------

@pytest.mark.asyncio
async def test_generate_identity_honours_an_explicitly_given_id(db_session):
    """The scheduler reserves a proxy for an id before the identity exists, so
    the identity has to be creatable under that exact id."""
    wanted = uuid4()
    identity = await identity_service.generate_identity(db_session, identity_id=wanted)
    assert identity.id == wanted


@pytest.mark.asyncio
async def test_generate_identity_still_generates_an_id_when_none_is_given(db_session):
    """Passing id=None explicitly would override the column default with a
    literal NULL, so the field is only set when a caller actually supplies one."""
    identity = await identity_service.generate_identity(db_session)
    assert identity.id is not None
