"""Runs email-creation pipelines, at most `concurrency` of them at a time.

Work arrives as jobs (see enqueue / enqueue_new): creating an identity that
needs a mailbox puts a job on this worker's queue and returns immediately, so
"Generate 20 identities" is 20 instant creations plus a queue, not 20 browsers.
The supervisor loop then pulls jobs off the queue as slots free up.

The flow, per slot:

    reserve a working proxy  ->  (generate the identity)  ->  run its pipeline

and the moment a pipeline finishes (success or failure) that slot immediately
takes the next queued job, so the cap is on how many run *at once*, never on
how many are asked for. Each slot is an independent asyncio.Task with its own DB
session, its own identity, its own proxy and its own start time - nothing here
waits on another slot's pipeline.

The proxy a slot reserves comes from whatever the proxy refresher worker
(app.workers.proxy_refresher) has most recently put in the table; this worker
never scrapes. When nothing in the pool is alive the slot waits and retries
rather than giving up, because a pipeline may never run unproxied.

In continuous mode the worker additionally invents its own work: whenever the
queue is empty it generates a fresh identity to keep every slot busy, so N
pipelines are always running rather than only when someone asks.
"""
from __future__ import annotations

import asyncio
import traceback
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.database import AsyncSessionLocal
from app.models.email_platform import EmailPlatform
from app.pipelines.email_pool import progress as pipeline_progress
from app.pipelines.email_pool.registry import PROVIDER_PIPELINES
from app.services import email_platform_service, identity_service
from app.workers.base import LoopWorker

# How many signup pipelines should be in flight simultaneously. Each one is a
# full Chromium instance, so this is the real resource knob.
DEFAULT_CONCURRENCY = 7
# How often the supervisor re-checks whether a slot has freed up. Short,
# because "when one finishes it starts another" should mean seconds, not
# minutes - and the check itself is just a set comprehension over done tasks.
TOPUP_INTERVAL_S = 2.0
# How long a slot waits before searching the pool again after coming up empty.
# The refresher replaces the list every 2 minutes, so retrying faster than
# this mostly re-tests the same dead rows.
NO_PROXY_RETRY_DELAY_S = 15.0
# Full passes over the pool that a slot will make, finding nothing alive,
# before it stops insisting on residential/mobile and accepts a datacenter
# proxy too. Datacenter ranges are much more likely to be pre-flagged by
# anti-abuse heuristics, so they stay a last resort - but a last resort is
# still better than a slot that never runs.
DATACENTER_AFTER_EMPTY_PASSES = 3


@dataclass
class _Job:
    """One queued pipeline run.

    identity_id is set when the identity already exists - which is the normal
    case: creating an identity without a mailbox enqueues it, so the row is in
    the database (and visible on the Identities page) the instant the request
    returns, long before a slot picks it up. It's None only for continuous
    mode, where the worker generates the identity itself once a slot is free.
    """

    platform_id: UUID
    identity_id: Optional[UUID] = None


class _CandidateQueue:
    """One shared cursor over the current proxy pool for all slots.

    take() hands out each candidate to exactly one slot, ever - which is the
    whole point: without it every slot independently queries the pool, gets the
    same freshest-first ordering, and health-checks the same top 20 rows
    concurrently, so six of the seven searches are pure waste.

    The read-and-advance in _take_now is synchronous with no await inside it,
    which on a single event loop makes it atomic - two slots physically cannot
    interleave there and receive the same row. Refilling does need I/O, so
    that part is serialised behind a lock, with a re-check after acquiring it
    so a slot that queued up behind someone else's refill uses that result
    instead of immediately querying again.
    """

    def __init__(self) -> None:
        self._items: list[identity_service.ProxyCandidate] = []
        self._pos = 0
        self._refill_lock = asyncio.Lock()
        self._refills = 0

    def _take_now(self, n: int) -> list[identity_service.ProxyCandidate]:
        batch = self._items[self._pos:self._pos + n]
        self._pos += len(batch)
        return batch

    @property
    def remaining(self) -> int:
        return max(0, len(self._items) - self._pos)

    @property
    def refills(self) -> int:
        return self._refills

    async def take(self, n: int, allow_datacenter: bool) -> list[identity_service.ProxyCandidate]:
        """The next n untested candidates, refilling from the DB when the
        current snapshot is used up. Returns [] only when the pool itself has
        nothing left to offer."""
        batch = self._take_now(n)
        if batch:
            return batch

        async with self._refill_lock:
            batch = self._take_now(n)
            if batch:
                return batch
            async with AsyncSessionLocal() as db:
                self._items = await identity_service.list_free_proxy_candidates(
                    db, allow_datacenter=allow_datacenter
                )
            self._pos = 0
            self._refills += 1
            return self._take_now(n)


class PipelineScheduler(LoopWorker):
    name = "pipeline-scheduler"
    interval_s = TOPUP_INTERVAL_S

    def __init__(self, concurrency: int = DEFAULT_CONCURRENCY) -> None:
        super().__init__()
        self.concurrency = concurrency
        # Only consulted in continuous mode, where there's no requester to say
        # which platform a run should use.
        self.email_platform_id: Optional[UUID] = None
        self.continuous = False
        self._jobs: deque[_Job] = deque()
        self._slots: set[asyncio.Task] = set()
        self._queue = _CandidateQueue()
        self._launched = 0
        self._failed_to_launch = 0

    # --- taking work -----------------------------------------------------
    def enqueue(self, identity_id: UUID, platform_id: UUID, display_name: Optional[str] = None,
                provider_name: str = "") -> int:
        """Queues an already-created identity for a pipeline run and returns
        the new queue depth. Starts the worker if it isn't running, so creating
        an identity is all anyone has to do - there's no separate "and also
        start the scheduler" step to forget.

        Synchronous and instant on purpose: the caller is an HTTP request
        handler, and the whole point of the queue is that requesting 20
        identities returns in the time it takes to write 20 rows."""
        self._jobs.append(_Job(platform_id=platform_id, identity_id=identity_id))
        # Recorded as queued right away so the wait for a slot is visible on
        # the Pipelines/Monitoring pages instead of looking like nothing
        # happened.
        pipeline_progress.queue(identity_id, provider_name, display_name=display_name)
        if not self.is_running():
            self.start()
        return len(self._jobs)

    def clear_queue(self) -> int:
        """Drops every job not yet started, returning how many. In-flight
        pipelines are left alone - use stop() for those."""
        dropped = len(self._jobs)
        for job in self._jobs:
            if job.identity_id is not None:
                pipeline_progress.finish(job.identity_id, error="removed from the queue before it started")
        self._jobs.clear()
        return dropped

    # --- lifecycle -------------------------------------------------------
    def configure(
        self,
        concurrency: Optional[int] = None,
        email_platform_id: Optional[UUID] = None,
        continuous: Optional[bool] = None,
    ) -> None:
        if concurrency is not None:
            self.concurrency = max(1, concurrency)
        if email_platform_id is not None:
            self.email_platform_id = email_platform_id
        if continuous is not None:
            self.continuous = continuous

    async def stop(self) -> bool:
        """Cancels the in-flight pipelines along with the supervisor loop -
        otherwise stopping the worker would leave up to `concurrency` Chromium
        instances running with nothing supervising them. Cancellation
        propagates into provider.run(), whose own `finally: browser.close()`
        still runs at its suspension point."""
        stopped = await super().stop()
        slots, self._slots = self._slots, set()
        for task in slots:
            task.cancel()
        if slots:
            await asyncio.gather(*slots, return_exceptions=True)
            self.log(f"cancelled {len(slots)} in-flight pipeline slot(s)")
        # Drop the candidate snapshot too: by the next start the refresher will
        # have replaced those rows, so keeping them would only mean
        # health-checking ids that no longer exist.
        self._queue = _CandidateQueue()
        return stopped

    def extra_status(self) -> dict:
        return {
            "concurrency": self.concurrency,
            "continuous": self.continuous,
            "active_slots": len([t for t in self._slots if not t.done()]),
            "queued": len(self._jobs),
            "email_platform_id": str(self.email_platform_id) if self.email_platform_id else None,
            "launched": self._launched,
            "failed_to_launch": self._failed_to_launch,
            "proxy_candidates_remaining": self._queue.remaining,
            "proxy_pool_refills": self._queue.refills,
        }

    # --- the supervisor --------------------------------------------------
    async def run_once(self) -> None:
        """Moves queued jobs into free slots, up to `concurrency`. Deliberately
        the whole of the supervisor's job: everything else - the proxy search,
        identity generation, the pipeline itself - happens inside a slot task,
        so a slot waiting minutes for a live proxy never holds up another slot
        from starting."""
        self._slots = {task for task in self._slots if not task.done()}
        free = self.concurrency - len(self._slots)
        if free <= 0:
            return

        started = 0
        for _ in range(free):
            job = self._next_job()
            if job is None:
                break
            try:
                platform = await self._resolve_platform(job.platform_id)
            except Exception as exc:
                # The job is already off the queue at this point, so put it back
                # rather than losing it to a transient database error - unlike a
                # platform with no pipeline (below), this may well work next tick.
                self._jobs.appendleft(job)
                self.log(f"could not resolve a queued job's platform, retrying: {type(exc).__name__}: {exc}")
                break
            if platform is None:
                self._reject(job)
                continue
            task = asyncio.create_task(self._run_slot(job, platform), name=f"{self.name}:slot")
            self._slots.add(task)
            started += 1

        if started:
            self.log(
                f"started {started} pipeline(s) - {len(self._slots)}/{self.concurrency} slots busy, "
                f"{len(self._jobs)} still queued"
            )

    def _next_job(self) -> Optional[_Job]:
        """The next queued job, or - in continuous mode with an empty queue - a
        synthesised one telling the slot to generate its own identity."""
        if self._jobs:
            return self._jobs.popleft()
        if self.continuous and self.email_platform_id is not None:
            return _Job(platform_id=self.email_platform_id, identity_id=None)
        return None

    def _reject(self, job: _Job) -> None:
        """A job whose platform can't actually be run. Dropped rather than
        retried: nothing about it will change on the next tick, and retrying it
        forever would keep the log scrolling while blocking the queue."""
        self._failed_to_launch += 1
        reason = (
            f"email platform {job.platform_id} has no automated signup pipeline "
            f"(available: {', '.join(sorted(PROVIDER_PIPELINES))})"
        )
        self.log(f"dropped a queued job: {reason}")
        if job.identity_id is not None:
            pipeline_progress.finish(job.identity_id, error=reason)

    async def _resolve_platform(self, platform_id: UUID) -> Optional[EmailPlatform]:
        """The platform a job runs against, or None if it can't be run.

        A platform with no registered pipeline is rejected rather than used.
        The slot would fail on it instantly - but only *after* reserving and
        consuming a proxy, so a queue full of such jobs would quietly burn the
        whole pool one job at a time."""
        async with AsyncSessionLocal() as db:
            platform = await email_platform_service.get_email_platform(db, platform_id)
        if platform is not None and platform.name.strip().lower() in PROVIDER_PIPELINES:
            return platform
        return None

    async def default_platform_id(self) -> Optional[UUID]:
        """First platform that actually has an automated pipeline - used to
        give continuous mode something to run when no platform was configured
        explicitly."""
        async with AsyncSessionLocal() as db:
            for platform in await email_platform_service.get_email_platforms(db):
                if platform.name.strip().lower() in PROVIDER_PIPELINES:
                    return platform.id
        return None

    # --- one slot --------------------------------------------------------
    async def _run_slot(self, job: _Job, platform: EmailPlatform) -> None:
        """One identity, start to finish. Returning frees the slot, which the
        supervisor refills from the queue on its next tick."""
        # For a continuous-mode job the id is decided here, before anything
        # exists, so the proxy can be reserved for it and the identity then
        # created under that same id - closing the window where a pipeline could
        # start before its proxy reservation landed.
        identity_id = job.identity_id or uuid.uuid4()
        try:
            proxy = await self._reserve_proxy(identity_id)

            if job.identity_id is None:
                async with AsyncSessionLocal() as db:
                    identity = await identity_service.generate_identity(db, identity_id=identity_id)
                    await db.commit()
                self.log(f"identity {identity.username} ({identity_id}) created on {proxy}, starting pipeline")
            else:
                self.log(f"identity {identity_id} got {proxy}, starting pipeline")
            self._launched += 1

            # Awaited, not fire-and-forget: this task IS the slot, so the slot
            # stays occupied for exactly as long as the pipeline runs and frees
            # the instant it ends. start_email_pipeline_for_identity handles
            # and records its own failures (including deleting the identity),
            # so a failure here is still a normal slot completion.
            await identity_service.start_email_pipeline_for_identity(
                identity_id, platform.name, platform.domain, platform.id, platform.type,
            )
        except asyncio.CancelledError:
            await self._release(identity_id)
            raise
        except Exception as exc:
            # A failure before the pipeline took over - most likely identity
            # creation. The proxy was already reserved at that point and
            # nothing else would ever hand it back (delete_identity can't
            # help for a continuous-mode job: there's no identity row), so
            # release it explicitly.
            self._failed_to_launch += 1
            error = f"{type(exc).__name__}: {exc}"
            self.log(f"slot failed before its pipeline started: {error}")
            print(traceback.format_exc())
            # The run never reached start_email_pipeline_for_identity, so
            # nothing else will move it off "queued" on the dashboard.
            pipeline_progress.finish(identity_id, error=f"failed before the pipeline started - {error}")
            await self._release(identity_id)

    async def _reserve_proxy(self, identity_id: UUID) -> str:
        """Searches the shared candidate queue until something alive is
        reserved for identity_id, returning a label for logging.

        Loops indefinitely rather than failing: a proxy is mandatory, and the
        refresher replaces the pool every couple of minutes, so "nothing works
        right now" is a reason to wait, not to run unproxied or to abandon the
        slot. Only cancellation ends the wait.

        Batches follow each other with no pause while the current pass still
        has untested rows; the delay is per *pass* over the pool, so a walk
        that comes back empty-handed waits for the refresher to put something
        new in the table instead of instantly re-testing the same dead rows in
        a tight loop."""
        def slot_log(message: str) -> None:
            # Both places on purpose: the worker log is the operator's view of
            # the scheduler, and the per-identity log is what the Pipelines page
            # shows for this run - so "still looking for a proxy" is visible
            # there too rather than the run just sitting silently queued.
            self.log(message)
            pipeline_progress.add_log(identity_id, message)

        empty_passes = 0
        while True:
            allow_datacenter = empty_passes >= DATACENTER_AFTER_EMPTY_PASSES
            async with AsyncSessionLocal() as db:
                batch = await self._queue.take(identity_service.PROXY_TEST_BATCH_SIZE, allow_datacenter)
                if batch:
                    proxy = await identity_service.test_and_reserve_from_batch(
                        db, batch, identity_id, log=slot_log
                    )
                    if proxy is not None:
                        return f"{proxy.host}:{proxy.port} ({proxy.type.value})"
                    if self._queue.remaining > 0:
                        # Nothing alive in this batch, but the pass has more
                        # untested rows - keep going without pausing.
                        continue

            empty_passes += 1
            if allow_datacenter:
                detail = "datacenter included as a last resort"
            else:
                remaining_passes = DATACENTER_AFTER_EMPTY_PASSES - empty_passes
                detail = f"residential/mobile only for {remaining_passes} more pass(es)"
            slot_log(
                f"no working proxy in the pool ({detail}) - waiting {NO_PROXY_RETRY_DELAY_S:.0f}s "
                "for the refresher to replace it"
            )
            await asyncio.sleep(NO_PROXY_RETRY_DELAY_S)

    async def _release(self, identity_id: UUID) -> None:
        try:
            async with AsyncSessionLocal() as db:
                released = await identity_service.release_proxy_reservations(db, identity_id)
            if released:
                self.log(f"released {released} unused proxy reservation(s) for {identity_id}")
        except Exception:
            print(f"[{self.name}] failed to release proxy reservations for {identity_id}:\n{traceback.format_exc()}")


# One instance per process - reachable from the /api/workers routes.
pipeline_scheduler = PipelineScheduler()
