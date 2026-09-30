from __future__ import annotations
import asyncio
import random
import string
import traceback
from datetime import datetime, timezone
from typing import Callable, NamedTuple, Optional
from uuid import UUID
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.database import AsyncSessionLocal
from app.models.email_platform import EmailPlatformType
from app.models.identity import Identity, IdentityStatus
from app.models.bot import Bot, BotStatus, BotState
from app.models.email import Email
from app.models.proxy import Proxy, ProxyType
from app.schemas.email import EmailCreate
from app.schemas.identity import IdentityCreate, IdentityUpdate
from app.auth.utils import hash_password
from app.services import email_service, proxy_service
from app.utilities.proxy_health import check_proxy_health
from app.pipelines.email_pool import manual_gate, progress as pipeline_progress
from app.pipelines.email_pool.registry import get_provider_pipeline

# Each identity's email pipeline is gated on its own manual_gate entry (see
# below) and runs in its own browser instance, so multiple can run fully
# concurrently as independent background tasks - nothing here serializes
# them process-wide anymore (it used to, back when the CAPTCHA step blocked
# on this process's own stdin and two browsers would have fought over one
# prompt; that's gone now that resuming goes through a per-identity gate).

PROXY_STEP_NAME = "select_and_test_proxy"
# Hard cap on one signup session's total wall-clock time. Every individual
# step wait inside the pipeline is deliberately unbounded (tuta.py's
# VERIFY_TIMEOUT_MS et al. are 0 - a slow-loading page shouldn't fail a step
# just because it's slow), but that means a session that genuinely never
# resolves (a proxy connection that hangs instead of erroring) would
# otherwise sit "running" forever, holding a whole Chromium instance in
# memory. This is the outer backstop for exactly that - see the
# asyncio.wait_for around provider.run() below.
SESSION_TIMEOUT_S = 300
# A proxy is mandatory - the pipeline never runs a single action unproxied
# (see start_email_pipeline_for_identity), so _select_and_test_proxy doesn't
# give up after one scrape+test pass either: it keeps re-scraping
# free-proxy-list and testing whatever's untested in the pool, round after
# round, until something comes back alive. Bounded rather than a literal
# `while True` so a genuinely proxy-less environment fails cleanly instead of
# hanging a background task forever.
MAX_PROXY_SCRAPE_ROUNDS = 20
# Re-scraping the exact same source instantly rarely turns up anything new -
# free-proxy-list rotates on the order of minutes, not seconds - so pause
# between rounds instead of hammering it back-to-back for no benefit.
PROXY_SCRAPE_ROUND_DELAY_S = 4
# How many untested candidates get health-checked concurrently at once,
# rather than one at a time - each check_proxy_health call can take up to
# its own 10s timeout, so testing them sequentially against a large,
# mostly-dead pool wastes real minutes waiting on dead ones one by one.
PROXY_TEST_BATCH_SIZE = 20
# How many proxies one signup run will burn through before giving up. A proxy
# that passes its health check can still fail the moment the browser actually
# uses it - the check probes one destination at one instant, and a free proxy
# can be dead, or blocked by this particular site, by the time Chromium opens a
# connection through it. Rather than failing the whole run on that, the run
# retires the proxy and starts over on a new one (see
# start_email_pipeline_for_identity). Bounded rather than a literal `while
# True` so a completely unusable pool fails cleanly instead of pinning a
# scheduler slot and a Chromium instance forever.
MAX_PROXY_ATTEMPTS_PER_RUN = 25
# A hung session gets a much smaller allowance than a fast failure. A Chrome
# network error comes back in seconds, so burning 25 proxies on those costs
# little; a hang costs minutes of wall clock each, and 25 of them would pin a
# scheduler slot and a Chromium instance for hours.
MAX_HUNG_SESSIONS_PER_RUN = 3
# How long one pipeline step may go without the run advancing to the next step
# before the whole session is killed. This is the real liveness check: every
# individual wait inside the pipeline is deliberately unbounded (tuta.py's
# VERIFY_TIMEOUT_MS et al. are 0, so a slow page never fails a step just for
# being slow), which means a step whose page never resolves would otherwise sit
# there indefinitely. Watching for *progress* rather than capping each step's
# duration is what lets a genuinely slow-but-moving run take as long as it
# needs while a stuck one dies promptly.
#
# A step marked manual is exempt - that one is waiting on a person by design,
# and there is no sense putting a stopwatch on a human.
STEP_STALL_TIMEOUT_S = 180

# Chrome network errors that mean "this proxy did not work", as opposed to
# "the signup flow itself went wrong". Everything here is a failure to get
# bytes through the proxy at all - a different proxy is a real fix, and
# retrying on the same one never is. Matched as substrings of the exception
# text because Playwright surfaces them inside a longer call-log message
# (e.g. 'Page.goto: net::ERR_TIMED_OUT at https://tuta.com/cs').
PROXY_FAILURE_MARKERS = (
    # Nothing answered at all - dead proxy, or one black-holing this destination.
    "ERR_TIMED_OUT",
    "ERR_CONNECTION_TIMED_OUT",
    # The proxy answered but refused/failed to tunnel the request.
    "ERR_TUNNEL_CONNECTION_FAILED",
    "ERR_PROXY_CONNECTION_FAILED",
    "ERR_SOCKS_CONNECTION_FAILED",
    "ERR_PROXY_AUTH_REQUESTED",
    "ERR_UNEXPECTED_PROXY_AUTH",
    # The proxy is intercepting TLS with its own certificate. Certificate
    # validation stays on deliberately (see tuta.py's new_context), so this
    # fails the run - and the proxy, not the site, is what's wrong.
    "ERR_CERT_AUTHORITY_INVALID",
    "ERR_CERT_COMMON_NAME_INVALID",
    "ERR_CERT_DATE_INVALID",
    "ERR_SSL_PROTOCOL_ERROR",
    # Answered, then dropped the connection part-way.
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_REFUSED",
    "ERR_CONNECTION_ABORTED",
    "ERR_CONNECTION_FAILED",
    "ERR_EMPTY_RESPONSE",
    "ERR_RESPONSE_HEADERS_TRUNCATED",
    # Never reachable in the first place.
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_NETWORK_CHANGED",
    "ERR_INTERNET_DISCONNECTED",
)

# Not a Chrome error: our own detection of Tuta's "this IP is blocked for
# suspected abuse" banner (see tuta.py's IP_BLOCKED_TEXT). The proxy works
# fine at the network level, but its IP is already burned for this site -
# which a new proxy fixes and a retry on the same one cannot.
IP_BLOCKED_MARKER = "ip_blocked"


def _is_proxy_failure(error_text: str) -> bool:
    """Whether this failure is the proxy's fault, and so worth retrying on a
    different one. Deliberately conservative: anything not listed (a missing
    selector, an unexpected page, a rejected username) is a problem with the
    signup flow or the site, and burning 25 proxies on it would only hide the
    real error behind a pile of retries."""
    if IP_BLOCKED_MARKER in error_text:
        return True
    return any(marker in error_text for marker in PROXY_FAILURE_MARKERS)


class StepStalledError(Exception):
    """Raised when a run stops advancing: the same pipeline step has been
    current for longer than STEP_STALL_TIMEOUT_S.

    Distinct from a step *failing* - nothing errored, the run simply stopped
    making progress, which in practice means a page that will never resolve
    (almost always a proxy whose connection hangs rather than refusing)."""


async def _run_until_stalled(
    coro,
    *,
    last_progress_at: Callable[[], float],
    is_waiting_on_human: Callable[[], bool],
    stall_timeout_s: float,
    overall_timeout_s: float,
):
    """Awaits coro, killing it if the pipeline stops advancing.

    Two independent guards, because they catch different things:
      - stall_timeout_s: no step change for this long. The primary one - it
        notices a wedged run within STEP_STALL_TIMEOUT_S no matter how long the
        run has been going, and equally lets a slow but steadily advancing run
        carry on indefinitely.
      - overall_timeout_s: total wall clock for the session, as a blunt
        backstop for anything the stall check could miss (a run that keeps
        changing steps forever, say).

    While the current step is manual the stall check is suspended: that step is
    waiting for a person on purpose, and killing it after three minutes would
    just be a race against how fast someone reads the dashboard.

    Cancelling and then awaiting the task is what actually stops the browser -
    cancellation resumes the provider coroutine at its suspension point, which
    runs its own `finally: browser.close()`. Returning without that await would
    leave a Chromium instance behind, which is the exact thing this guard
    exists to prevent.
    """
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(coro)
    started_at = loop.time()
    # Frequent enough that the reported stall time is close to the real one,
    # cheap enough to be irrelevant next to a browser session. Bounded by BOTH
    # limits: polling every 5s would otherwise overshoot a short overall_timeout
    # by most of a poll interval, which matters to the tests that drive this
    # with sub-second values far more than it does in production.
    poll_s = max(0.01, min(5.0, stall_timeout_s / 4, overall_timeout_s / 4))

    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=poll_s)
            if done:
                return task.result()

            now = loop.time()
            if now - started_at >= overall_timeout_s:
                raise asyncio.TimeoutError()
            if is_waiting_on_human():
                continue
            stalled_for = now - last_progress_at()
            if stalled_for >= stall_timeout_s:
                raise StepStalledError(
                    f"no pipeline step change for {stalled_for:.0f}s "
                    f"(limit {stall_timeout_s:.0f}s) - terminating the session"
                )
    finally:
        if not task.done():
            task.cancel()
            # asyncio.wait rather than `await task`: it waits for the
            # cancellation to actually complete (which is what lets the
            # provider's own finally: browser.close() run) without re-raising
            # the run's exception here, and without swallowing a cancellation
            # aimed at *this* coroutine - the scheduler cancels slots to stop
            # them, and eating that would leave the slot looking like it
            # finished normally.
            await asyncio.wait({task})
        if not task.cancelled():
            # Retrieve any exception so asyncio doesn't log it as never
            # retrieved. Whatever the run raised on its way out is not the
            # failure worth reporting - the stall or the timeout is.
            task.exception()


async def flag_proxy_not_working(proxy_id: UUID, reason: str) -> None:
    """Flags a proxy that failed in real use so nothing else picks it up, and
    deliberately does NOT blacklist it.

    Three things happen, and the third is the point:
      - is_healthy=False, which is what actually excludes it from every
        candidate search (see list_free_proxy_candidates and
        _select_and_test_proxy) and makes it read as dead on the Proxies page.
      - assigned_bot_id cleared, so it's no longer locked to the identity whose
        run it just failed.
      - consumed_at cleared. consumed_at means "an account was registered
        through this IP" and is permanent - a proxy that couldn't even get bytes
        through never registered anything, so marking it consumed would
        blacklist a possibly-fine address from every future import forever.

    Net effect: unusable by any other identity for now, but a normal free row
    again - so the proxy refresher's next cycle drops it with the rest of the
    stale pool and re-imports it if the source still lists it, at which point
    it's a fresh candidate with is_healthy=True. "Out of the list until the next
    import", not "gone for good".

    Opens its own session: this is called from inside a pipeline run's own
    error handling, where the caller's session may already be gone."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Proxy)
            .where(Proxy.id == proxy_id)
            .values(
                is_healthy=False,
                last_checked=datetime.now(timezone.utc),
                assigned_bot_id=None,
                consumed_at=None,
            )
        )
        await db.commit()
    print(f"[proxy {proxy_id}] flagged not working: {reason}")


async def _claim_and_consume_free_proxy(db: AsyncSession, proxy_id: UUID, identity_id: UUID) -> bool:
    """Atomically claims this proxy out of the free pool - concurrent
    pipelines run without any process-wide lock now, so two identities could
    otherwise both see the same 'free' proxy as a candidate at the same time
    and both try to use it. UPDATE ... WHERE assigned_bot_id IS NULL AND
    consumed_at IS NULL is the guard: whichever caller's statement actually
    matches a row (rowcount == 1) won the claim; the loser sees rowcount == 0
    and moves on to its next candidate instead of double-using the same IP
    for two accounts.

    Sets consumed_at rather than deleting the row (see the Proxy model) - a
    proxy that's ever actually been handed to a pipeline must never be
    reused, not even after this identity is later deleted, and the row
    needs to keep existing so import_proxies_from_free_list's host:port
    dedup check keeps recognizing it if the exact same IP ever gets scraped
    again."""
    result = await db.execute(
        sa_update(Proxy)
        .where(Proxy.id == proxy_id, Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
        .values(assigned_bot_id=identity_id, consumed_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return result.rowcount == 1


async def _reserve_free_proxy_for(db: AsyncSession, proxy_id: UUID, identity_id: UUID) -> bool:
    """Reserve-only sibling of _claim_and_consume_free_proxy: sets
    assigned_bot_id but deliberately NOT consumed_at, using the same atomic
    "only if still free" guard so two concurrent callers can't both take it.

    The distinction matters - consumed_at means "a pipeline actually used
    this", and it's what permanently retires a proxy. A reservation is the
    earlier half of that: the pipeline's own proxy step
    (_select_and_test_proxy's assigned fast path) is what later consumes it,
    which also means it finds the proxy waiting for it and skips re-testing
    and scraping entirely. Reserving without consuming also keeps the
    proxy recoverable - delete_identity releases an unconsumed reservation
    back to the pool if the identity never gets that far."""
    result = await db.execute(
        sa_update(Proxy)
        .where(Proxy.id == proxy_id, Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
        .values(assigned_bot_id=identity_id)
    )
    await db.commit()
    return result.rowcount == 1


async def release_proxy_reservations(db: AsyncSession, identity_id: UUID) -> int:
    """Hands back any proxy reserved for this identity that no pipeline has
    actually consumed yet. For the case delete_identity can't cover: the
    scheduler reserves a proxy *before* creating the identity, so if creation
    itself fails there's no identity row to delete and nothing else would
    ever release the reservation - the proxy would sit assigned to an id that
    never existed, invisible to every future search. Consumed proxies are
    left alone: those are permanently retired on purpose."""
    result = await db.execute(
        sa_update(Proxy)
        .where(Proxy.assigned_bot_id == identity_id, Proxy.consumed_at.is_(None))
        .values(assigned_bot_id=None)
    )
    await db.commit()
    return result.rowcount or 0


class ProxyCandidate(NamedTuple):
    """A session-independent snapshot of one poolable proxy: exactly the
    fields a health check needs, plus the id to reserve by.

    Plain data rather than an ORM row on purpose - the pipeline scheduler
    shares one candidate list across slots that each own a separate DB
    session, and handing Proxy instances between sessions is the kind of thing
    that works until someone changes expire_on_commit."""

    id: UUID
    host: str
    port: int
    protocol: str
    type: str
    username: Optional[str]
    password: Optional[str]

    @property
    def label(self) -> str:
        return f"{self.host}:{self.port} ({self.type})"


async def list_free_proxy_candidates(
    db: AsyncSession,
    allow_datacenter: bool = False,
) -> list[ProxyCandidate]:
    """Every proxy currently available to be handed to a new identity:
    unreserved, never consumed, not flagged as broken, and of an acceptable
    type. Ordered most-recently-checked first, so the candidates with the
    freshest evidence behind them get tried before stale ones.

    is_healthy is a filter here rather than just a sort key. A proxy that has
    failed - either its last health check or, worse, a real pipeline run through
    it (see flag_proxy_not_working) - must not be handed straight back out to
    the next identity that comes looking. It isn't blacklisted either: the proxy
    refresher replaces the free pool every couple of minutes, and a row that
    comes back from that import is healthy again and fair game.

    Split out from the test-and-reserve half below so the pipeline scheduler
    can hold ONE shared list across all of its concurrent slots (see
    app.workers.pipeline_scheduler) instead of every slot independently
    querying and then health-checking the same top-of-the-list candidates -
    which is pure duplicated work, and was a real bug in the frontend's
    batch-generate flow before the same fix was applied there."""
    allowed_types = (ProxyType.residential, ProxyType.mobile)
    if allow_datacenter:
        allowed_types = allowed_types + (ProxyType.datacenter,)

    result = await db.execute(
        select(
            Proxy.id, Proxy.host, Proxy.port, Proxy.protocol,
            Proxy.type, Proxy.username, Proxy.password,
        )
        .where(
            Proxy.assigned_bot_id.is_(None),
            Proxy.consumed_at.is_(None),
            Proxy.is_healthy.is_(True),
            Proxy.type.in_(allowed_types),
        )
        .order_by(Proxy.last_checked.desc())
    )
    return [
        ProxyCandidate(
            id=row.id, host=row.host, port=row.port,
            protocol=row.protocol.value, type=row.type.value,
            username=row.username, password=row.password,
        )
        for row in result.all()
    ]


async def test_and_reserve_from_batch(
    db: AsyncSession,
    batch: list[ProxyCandidate],
    identity_id: UUID,
    log: Callable[[str], None] = lambda msg: None,
) -> Optional[Proxy]:
    """Health-checks one batch of candidates concurrently and reserves the
    first live one for identity_id, returning it as a live Proxy row. Dead
    ones are marked unhealthy so a later search deprioritises them (until the
    refresher replaces the row outright).

    Returns None if nothing in this batch was usable - either dead, or alive
    but reserved by another caller in the same instant, which the atomic
    _reserve_free_proxy_for guard turns into "try the next one" rather than
    two identities sharing one IP."""
    healthy_flags = await asyncio.gather(*(
        asyncio.to_thread(
            check_proxy_health, candidate.host, candidate.port, candidate.protocol,
            username=candidate.username, password=candidate.password,
        )
        for candidate in batch
    ))
    for candidate, healthy in zip(batch, healthy_flags):
        if not healthy:
            await db.execute(
                sa_update(Proxy)
                .where(Proxy.id == candidate.id)
                .values(is_healthy=False, last_checked=datetime.now(timezone.utc))
            )
            await db.commit()
            continue
        if await _reserve_free_proxy_for(db, candidate.id, identity_id):
            log(f"reserved {candidate.label}")
            return await db.get(Proxy, candidate.id)
    return None


async def claim_working_proxy_for_identity(
    db: AsyncSession,
    identity_id: UUID,
    log: Callable[[str], None] = lambda msg: None,
    allow_datacenter: bool = False,
) -> Optional[Proxy]:
    """Tests whatever is in the pool right now and reserves the first proxy
    that comes back alive for identity_id.

    Deliberately does NOT scrape: the proxy refresher worker (see
    app.workers.proxy_refresher) owns keeping the pool stocked on its own
    2-minute cycle, so this works with what's currently there and returns
    None when none of it is alive - leaving the caller to wait for the next
    refresh rather than duplicating scrape-and-retry logic here. That's the
    whole difference from _select_and_test_proxy, which still owns the
    self-sufficient scrape-then-test path for identities created outside the
    scheduler (e.g. straight through the API).

    Reserve-only (see _reserve_free_proxy_for) - the pipeline's own proxy
    step consumes it afterwards."""
    candidates = await list_free_proxy_candidates(db, allow_datacenter=allow_datacenter)
    if not candidates:
        return None

    log(f"testing up to {len(candidates)} pooled candidate(s), {PROXY_TEST_BATCH_SIZE} at a time")
    for batch_start in range(0, len(candidates), PROXY_TEST_BATCH_SIZE):
        batch = candidates[batch_start:batch_start + PROXY_TEST_BATCH_SIZE]
        proxy = await test_and_reserve_from_batch(db, batch, identity_id, log=log)
        if proxy is not None:
            return proxy

    return None


async def _select_and_test_proxy(
    db: AsyncSession,
    identity_id: UUID,
    log: Callable[[str], None] = lambda msg: None,
) -> Optional[Proxy]:
    """If the identity already has an unconsumed proxy assigned to it (the
    pipeline scheduler reserves one before creating the identity, and the
    Identities page's generation flow live-tests candidates via the same "Test"
    endpoint and assigns one before the identity is even created - see
    selectAndVerifyProxies in the frontend), that's just used directly: the
    freshest-checked assigned one is consumed as-is, with no re-test and no
    pool refresh, since it was already proven alive moments ago as part of
    generation and repeating that work here would only slow pipeline start down
    for nothing.

    Type is deliberately not re-filtered on that fast path. Whoever made the
    reservation already applied the residential/mobile preference and only
    escalated to datacenter after exhausting the alternatives; second-guessing
    that here would both throw away a proxy that was just proven alive and
    leak the reservation - the row would stay assigned to this identity while
    the pipeline went off to scrape, and nothing would ever hand it back.

    Only falls back to the scrape-then-select-from-the-pool flow (refreshing
    with fresh candidates from free-proxy-list, then testing what the pool
    has via check_proxy_health) when the identity has no such assigned proxy
    to begin with - e.g. an identity created directly through the API rather
    than the Identities page's generation flow. That fallback doesn't give up
    after one pass either: a proxy is mandatory (see
    start_email_pipeline_for_identity, which refuses to run a single pipeline
    action without one), so it keeps re-scraping and re-testing, round after
    round (see MAX_PROXY_SCRAPE_ROUNDS), until something comes back alive or
    the round budget runs out. No country preference anywhere in this - any
    residential/mobile proxy is fair game regardless of the identity's own
    country. Either way, the chosen proxy is marked consumed (see the Proxy
    model's consumed_at) rather than deleted, so it can never be reused for a
    second identity/account - not now, and not after a later free-proxy-list
    scrape happens to turn up the exact same host:port again. Returns None
    only once the entire round budget is exhausted with nothing usable found.

    Residential and mobile proxies are preferred throughout the pool search -
    datacenter ranges are far more likely to already be flagged by a site's
    anti-abuse heuristics, which is exactly the failure mode observed testing
    this pipeline live. But a proxy is mandatory (see start_email_pipeline_for_identity) and
    running unproxied is never an option, so the free-pool search's very
    last round also allows datacenter proxies as a last resort - worse odds
    of working cleanly, but still strictly better than refusing to run at
    all when nothing residential/mobile panned out after a full search.

    log(message), if given, is called with human-readable notes about what
    happened here (which path was taken, pool-refresh results) - the caller
    wires this to both stdout and pipeline_progress so it's visible on the
    Monitoring page's log viewer, not just the backend's own terminal."""
    ALLOWED_PROXY_TYPES = (ProxyType.residential, ProxyType.mobile)

    assigned = await db.execute(
        select(Proxy)
        .where(
            Proxy.assigned_bot_id == identity_id,
            Proxy.consumed_at.is_(None),
        )
        .order_by(Proxy.last_checked.desc())
    )
    assigned_proxies = assigned.scalars().all()
    if assigned_proxies:
        proxy = assigned_proxies[0]
        result = await db.execute(
            sa_update(Proxy)
            .where(Proxy.id == proxy.id, Proxy.assigned_bot_id == identity_id, Proxy.consumed_at.is_(None))
            .values(consumed_at=datetime.now(timezone.utc))
        )
        await db.commit()
        if result.rowcount == 1:
            log(
                f"using proxy already selected and verified during identity generation "
                f"({len(assigned_proxies)} assigned, freshest-checked one used) - "
                f"no re-test or pool refresh needed"
            )
            return proxy
        log("assigned proxy vanished before it could be claimed here - falling back to the pool")

    # No usable pre-assigned proxy - keep re-scraping and re-testing the pool
    # until something comes back alive. A single pass isn't enough: a dead
    # top-15 doesn't mean the whole pool is dead, and free-proxy-list itself
    # can simply have nothing alive on this particular pass. country plays no
    # part in candidate order here - any residential/mobile proxy works.
    for round_num in range(1, MAX_PROXY_SCRAPE_ROUNDS + 1):
        # The very last round also allows datacenter proxies - if nothing
        # residential/mobile has panned out after every other round, that's
        # "no other way" territory; a worse-odds proxy still beats refusing
        # to run at all.
        is_last_resort_round = round_num == MAX_PROXY_SCRAPE_ROUNDS
        round_types = ALLOWED_PROXY_TYPES + (ProxyType.datacenter,) if is_last_resort_round else ALLOWED_PROXY_TYPES

        # Round 1 works with the pool exactly as it is. The proxy refresher
        # worker (app.workers.proxy_refresher) replaces it every 2 minutes, so
        # what's already in the table is normally fresher than anything a scrape
        # here would add - and scraping first cost a full ~1800-row fetch before
        # a single candidate got tested, multiplied by however many pipelines
        # were searching at the time. Later rounds do scrape: reaching one means
        # nothing currently in the pool worked, so new candidates are the only
        # way forward.
        if round_num > 1:
            refresh = await proxy_service.import_proxies_from_free_list(db)
            if refresh.get("error"):
                log(f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: proxy pool refresh failed: {refresh['error']} - continuing with existing pool")
            else:
                log(
                    f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: refreshed proxy pool: "
                    f"{refresh.get('imported', 0)} new, {refresh.get('skipped', 0)} already known"
                )
        if is_last_resort_round:
            log(f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: no residential/mobile proxy found - allowing datacenter as a last resort")

        # Ordered by last_checked descending (freshest health data first) - a
        # proxy's actual liveness can change within minutes for cheap/public
        # sources, so a check from 5 minutes ago is far more trustworthy than
        # one from 2 days ago, and this order means the still-accurate
        # results get used before the stale ones waste a real test call. No
        # limit - a dead top N one round doesn't mean the rest of the pool
        # is dead too, and giving up early is exactly what mandatory-proxy
        # means not doing.
        #
        # Already-failed proxies are filtered out, not merely sorted last: one
        # that failed its check earlier in this very loop, or failed a real run
        # through it (see flag_proxy_not_working), would otherwise be re-tested
        # on the next round for nothing. Later rounds make progress by importing
        # NEW candidates instead - which is also what keeps "each proxy tested
        # once" true across rounds, not just within one.
        free = await db.execute(
            select(Proxy)
            .where(
                Proxy.assigned_bot_id.is_(None),
                Proxy.type.in_(round_types),
                Proxy.consumed_at.is_(None),
                Proxy.is_healthy.is_(True),
            )
            .order_by(Proxy.last_checked.desc())
        )
        candidates = free.scalars().all()
        log(f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: testing {len(candidates)} untested candidate(s)")

        # Tested PROXY_TEST_BATCH_SIZE at a time, concurrently, rather than
        # one at a time - a dead/slow candidate otherwise burns its whole
        # timeout before the next one even starts, and with a pool this size
        # (and this unreliable) that adds up to real minutes wasted.
        tested_count = 0
        for batch_start in range(0, len(candidates), PROXY_TEST_BATCH_SIZE):
            batch = candidates[batch_start:batch_start + PROXY_TEST_BATCH_SIZE]
            healthy_flags = await asyncio.gather(*(
                asyncio.to_thread(
                    check_proxy_health, proxy.host, proxy.port, proxy.protocol.value,
                    username=proxy.username, password=proxy.password,
                )
                for proxy in batch
            ))
            tested_count += len(batch)

            for proxy, healthy in zip(batch, healthy_flags):
                if not healthy:
                    proxy.is_healthy = False
                    proxy.last_checked = datetime.now(timezone.utc)
                    await db.commit()
                    continue
                if await _claim_and_consume_free_proxy(db, proxy.id, identity_id):
                    log(f"found a live proxy on round {round_num} after testing {tested_count} candidate(s) this round")
                    return proxy
                # Someone else's concurrent pipeline claimed it first - the
                # next alive candidate in this same batch (or a later one)
                # gets tried instead of giving up on the whole round.

        if round_num < MAX_PROXY_SCRAPE_ROUNDS:
            await asyncio.sleep(PROXY_SCRAPE_ROUND_DELAY_S)

    log(f"no live residential/mobile proxy found after {MAX_PROXY_SCRAPE_ROUNDS} rounds of scraping and testing")
    return None


def _proxy_to_playwright_config(proxy: Proxy) -> dict:
    config = {"server": f"{proxy.protocol.value}://{proxy.host}:{proxy.port}"}
    if proxy.username:
        config["username"] = proxy.username
    if proxy.password:
        config["password"] = proxy.password
    return config


async def get_identities(
    db: AsyncSession,
    status: Optional[str] = None,
    provider: Optional[str] = None,
) -> list:
    q = select(Identity)
    if status:
        q = q.where(Identity.status == status)
    if provider:
        q = q.where(Identity.email_provider == provider)
    result = await db.execute(q)
    return result.scalars().all()


async def get_identity(db: AsyncSession, identity_id: UUID) -> Optional[Identity]:
    result = await db.execute(select(Identity).where(Identity.id == identity_id))
    return result.scalar_one_or_none()


async def create_identity(db: AsyncSession, data: IdentityCreate) -> Identity:
    if data.email is not None:
        existing_email = await db.execute(select(Identity.id).where(Identity.email == data.email))
        if existing_email.scalar_one_or_none() is not None:
            raise ValueError(f"Identity with email '{data.email}' already exists")

    existing_username = await db.execute(select(Identity.id).where(Identity.username == data.username))
    if existing_username.scalar_one_or_none() is not None:
        raise ValueError(f"Identity with username '{data.username}' already exists")

    hashed = hash_password(data.password)
    identity_kwargs = {
        **data.model_dump(exclude={"id", "password", "email_platform_id", "proxy_id"}),
        "password_hash": hashed,
    }
    if data.id is not None:
        # Caller-supplied id (see IdentityCreate.id) - only set explicitly
        # when given, since passing id=None outright would override the
        # column's default=uuid.uuid4 with a literal NULL instead of
        # falling back to it.
        identity_kwargs["id"] = data.id
    identity = Identity(**identity_kwargs)
    db.add(identity)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Identity with the same email or username already exists")
    await db.refresh(identity)

    if data.proxy_id is not None:
        # Claimed atomically, in the same request/transaction that creates
        # the identity - guaranteed committed before the background pipeline
        # task is ever scheduled (see IdentityCreate.proxy_id). Best-effort:
        # if this proxy was somehow already claimed or consumed by the time
        # we get here (a real race, not the one this fixes), identity
        # creation still succeeds - the pipeline's own _select_and_test_proxy
        # falls back to scraping+testing the pool for a fresh one instead.
        await db.execute(
            sa_update(Proxy)
            .where(Proxy.id == data.proxy_id, Proxy.assigned_bot_id.is_(None), Proxy.consumed_at.is_(None))
            .values(assigned_bot_id=identity.id)
        )
        await db.commit()

    return identity


async def update_identity(db: AsyncSession, identity_id: UUID, data: IdentityUpdate) -> Optional[Identity]:
    identity = await get_identity(db, identity_id)
    if not identity:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(identity, field, value)
    await db.flush()
    return identity


async def delete_identity(db: AsyncSession, identity_id: UUID) -> bool:
    identity = await get_identity(db, identity_id)
    if not identity:
        return False

    bots_result = await db.execute(select(Bot).where(Bot.identity_id == identity_id))
    bots = bots_result.scalars().all()

    for bot in bots:
        # Release all emails assigned to this bot.
        emails_result = await db.execute(select(Email).where(Email.used_by_bot_id == bot.id))
        emails = emails_result.scalars().all()
        for email in emails:
            email.used_by_bot_id = None

        # Release proxy assignment by both relation pointers - but only ones
        # never actually consumed by a pipeline (consumed_at is None). A
        # consumed proxy must never be reused, not even once the identity/bot
        # that used it is gone - releasing it here would put it right back
        # in the free pool for someone else to pick up.
        if bot.proxy_id:
            proxy = await db.get(Proxy, bot.proxy_id)
            if proxy and proxy.consumed_at is None:
                proxy.assigned_bot_id = None
            bot.proxy_id = None
        proxy_by_bot_result = await db.execute(
            select(Proxy).where(Proxy.assigned_bot_id == bot.id, Proxy.consumed_at.is_(None))
        )
        proxies = proxy_by_bot_result.scalars().all()
        for proxy in proxies:
            proxy.assigned_bot_id = None

        # Detach bot from identity and reset lifecycle state.
        bot.identity_id = None
        bot.state = BotState.not_active
        bot.status = BotStatus.stopped

    # Proxies assigned straight to the identity itself (the Identities
    # page's generation flow does this before the identity even has a bot -
    # see selectAndVerifyProxies in the frontend) - same never-release-once-
    # consumed rule. Without this, an identity deleted before its pipeline
    # ever reached the proxy step (e.g. an unsupported provider) would leak
    # its still-unused assigned proxy forever: nothing else ever looks for
    # proxies pointing at a since-deleted identity id, so it'd sit locked out
    # of the pool with no way back in.
    identity_proxies_result = await db.execute(
        select(Proxy).where(Proxy.assigned_bot_id == identity_id, Proxy.consumed_at.is_(None))
    )
    for proxy in identity_proxies_result.scalars().all():
        proxy.assigned_bot_id = None

    await db.delete(identity)
    return True


def _random_str(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


async def generate_identity(db: AsyncSession, identity_id: Optional[UUID] = None) -> Identity:
    names = ["Alex", "Jordan", "Casey", "Morgan", "Taylor", "Riley", "Drew"]
    first = random.choice(names)
    last = _random_str(5).capitalize()
    username = f"{first.lower()}_{last.lower()}_{random.randint(100, 999)}"
    fields = dict(
        display_name=f"{first} {last}",
        username=username,
        # email / email_provider stay unset here - start_email_pipeline_for_identity
        # fills them in once the real mailbox has been created.
        password_hash=hash_password(_random_str(12)),
        location=random.choice(["US", "UK", "CA", "AU", "DE"]),
        age=random.randint(20, 45),
        interests=random.sample(["tech", "sports", "music", "gaming", "travel", "food"], 3),
        browser_profile_id=f"bp_{_random_str(8)}",
        browser_profile_provider="adspower",
        status=IdentityStatus.fresh,
    )
    if identity_id is not None:
        # Caller decided the id up front - the pipeline scheduler reserves a
        # proxy for an id before the identity exists (see
        # claim_working_proxy_for_identity), so the identity has to be created
        # under that same id for the two to line up. Only set when given,
        # since passing id=None explicitly would override the column's
        # default=uuid.uuid4 with a literal NULL instead of falling back to it.
        fields["id"] = identity_id
    identity = Identity(**fields)
    db.add(identity)
    await db.flush()
    await db.refresh(identity)
    return identity


async def _delete_failed_identity(identity_id: UUID) -> None:
    """A failed pipeline leaves an identity with no email and no real
    account behind it - not worth keeping around. The failure itself stays
    visible on the Pipelines/Monitoring pages regardless (pipeline_progress
    entries are self-contained - display_name/proxy/error/logs are stored
    there directly, not looked up live from the Identity row), so deleting
    here doesn't hide what happened."""
    try:
        async with AsyncSessionLocal() as db:
            deleted = await delete_identity(db, identity_id)
            await db.commit()
            if deleted:
                print(f"[identity {identity_id}] removed after pipeline failure")
    except Exception:
        print(f"[identity {identity_id}] failed to clean up after pipeline failure:\n{traceback.format_exc()}")


async def start_email_pipeline_for_identity(
    identity_id: UUID,
    provider_name: str,
    domain: str,
    platform_id: UUID,
    platform_type: EmailPlatformType,
) -> None:
    """Runs the chosen provider's signup pipeline for a just-created identity
    and attaches the resulting mailbox once it's done - both onto the
    identity itself (email / email_provider / email_password) and as a real
    Email row (see app.services.email_service) so the new mailbox shows up
    on the Email Accounts page like any other, poolable and assignable to a
    bot later. Live progress (including raw Playwright log lines - see
    on_log below) is tracked in app.pipelines.email_pool.progress for the
    dashboard's Pipelines and Monitoring pages (GET
    /api/identities/pipeline-status) to poll. On any failure the identity
    itself is deleted (see _delete_failed_identity) - the pipeline_progress
    record survives that and is what the dashboard actually reads, so the
    failure and its error/logs stay visible either way.

    Fire-and-forget: intended to be scheduled via FastAPI's BackgroundTasks
    right after the identity is created/generated, so the HTTP response
    doesn't wait on a multi-minute, human-in-the-loop browser pipeline. Opens
    its own DB session since the request-scoped one will already be closed by
    the time this finishes.
    """
    async with AsyncSessionLocal() as db:
        identity_row = await db.get(Identity, identity_id)
        display_name = identity_row.display_name if identity_row else None
        identity_age = identity_row.age if identity_row else None

    try:
        provider = get_provider_pipeline(provider_name)
    except ValueError as exc:
        pipeline_progress.start(identity_id, provider_name, [], display_name=display_name)
        pipeline_progress.finish(identity_id, error=str(exc))
        print(f"[identity {identity_id}] {exc}")
        await _delete_failed_identity(identity_id)
        return

    # select_and_test_proxy runs before any of the provider's own steps -
    # index 0 is reserved for it, so on_step below shifts the provider's
    # indices up by one to make room.
    steps = [{"name": PROXY_STEP_NAME, "manual": False}] + provider.describe()
    pipeline_progress.start(identity_id, provider_name, steps, display_name=display_name)

    # The run's liveness signal. Every step change stamps the clock; the stall
    # guard (see _run_until_stalled) kills the session when it stops being
    # stamped. Mutable containers rather than plain locals so the nested
    # callback can write to them without `nonlocal` gymnastics across the
    # per-attempt retry loop below.
    last_step_at = [0.0]
    waiting_on_human = [False]

    def on_step(index: int, step) -> None:
        last_step_at[0] = asyncio.get_running_loop().time()
        waiting_on_human[0] = bool(step.manual)
        pipeline_progress.update_step(identity_id, index + 1, step.name, step.manual)

    def on_log(message: str) -> None:
        pipeline_progress.add_log(identity_id, message)

    def proxy_log(message: str) -> None:
        print(f"[identity {identity_id}] {message}")
        on_log(message)

    try:
        result = None
        hung_sessions = 0
        # One attempt per proxy. A proxy that fails in real use is retired and
        # the whole run starts over on a fresh one, because a proxy failure
        # says nothing about whether the signup itself would work - see
        # MAX_PROXY_ATTEMPTS_PER_RUN and _is_proxy_failure. A failure that
        # isn't the proxy's fault breaks out immediately instead.
        for attempt in range(1, MAX_PROXY_ATTEMPTS_PER_RUN + 1):
            # Recreated per attempt: a gate left over from a previous attempt
            # could already be resumed, which would let a manual step sail
            # straight through on the retry without anyone confirming anything.
            #
            # Resumed by POST /api/identities/{id}/pipeline-status/continue -
            # not by this process's own stdin, which a backgrounded/nohup'd
            # server doesn't have an interactive one of (input() there raised
            # EOFError immediately, aborting the pipeline and closing the
            # browser right at the CAPTCHA step).
            gate = manual_gate.create(identity_id)

            async def wait_for_manual(prompt: str, _gate=gate) -> None:
                await _gate.wait()

            pipeline_progress.update_step(identity_id, 0, PROXY_STEP_NAME, False)
            async with AsyncSessionLocal() as db:
                proxy = await _select_and_test_proxy(db, identity_id, log=proxy_log)

            if proxy is None:
                # No proxy, no run - not even one step. Signing up straight from
                # the backend machine's own IP is exactly the exposure a proxy
                # exists to prevent, so a dead/empty pool fails the pipeline
                # outright (same cleanup as any other failure - see
                # _delete_failed_identity) rather than quietly falling back to
                # unproxied. provider.run() is never reached on this path.
                error_msg = (
                    f"no healthy proxy available (residential/mobile, or datacenter as a last "
                    f"resort) after {MAX_PROXY_SCRAPE_ROUNDS} scrape rounds on attempt "
                    f"{attempt}/{MAX_PROXY_ATTEMPTS_PER_RUN} - refusing to run without one"
                )
                proxy_log(error_msg)
                pipeline_progress.set_proxy(identity_id, None)
                pipeline_progress.finish(identity_id, error=error_msg)
                await _delete_failed_identity(identity_id)
                return

            proxy_id = proxy.id
            proxy_label = f"{proxy.host}:{proxy.port}"
            proxy_log(
                f"attempt {attempt}/{MAX_PROXY_ATTEMPTS_PER_RUN}: using proxy {proxy_label} "
                f"(type={proxy.type.value}, protocol={proxy.protocol.value}, country={proxy.country}) "
                f"- removed from the pool, will not be reused"
            )
            proxy_config = _proxy_to_playwright_config(proxy)
            # Belt-and-suspenders: the branch above already returns before this
            # point whenever proxy is None, so this can never actually fire - but
            # it makes "never run unproxied" a hard, load-bearing invariant
            # instead of just an artifact of the current control flow, so a
            # future edit that accidentally breaks that early return fails loudly
            # right here instead of silently signing up from the backend's own IP.
            assert proxy_config.get("server"), "refusing to run the pipeline with an empty proxy config"
            pipeline_progress.set_proxy(identity_id, {
                "host": proxy.host,
                "port": proxy.port,
                "type": proxy.type.value,
                "protocol": proxy.protocol.value,
                "country": proxy.country,
            })

            # Reset per attempt: the clock measures progress within this
            # session, and a retry starts a brand new browser.
            last_step_at[0] = asyncio.get_running_loop().time()
            waiting_on_human[0] = False
            try:
                result = await _run_until_stalled(
                    provider.run(
                        on_step=on_step,
                        wait_for_manual=wait_for_manual,
                        proxy=proxy_config,
                        display_name=display_name,
                        age=identity_age,
                        on_log=on_log,
                    ),
                    last_progress_at=lambda: last_step_at[0],
                    is_waiting_on_human=lambda: waiting_on_human[0],
                    stall_timeout_s=STEP_STALL_TIMEOUT_S,
                    overall_timeout_s=SESSION_TIMEOUT_S,
                )
                break
            except StepStalledError as exc:
                # The run stopped advancing. Every per-step wait inside the
                # pipeline is deliberately unbounded (see tuta.py's
                # VERIFY_TIMEOUT_MS - a step should wait for its target no
                # matter how slowly the page is loading, not fail just because
                # loading is taking a while), so this is what actually catches a
                # step whose page will never resolve, instead of it holding a
                # whole Chromium instance until the session cap runs out.
                #
                # Counted as a proxy failure: a step that produces nothing for
                # three minutes with no error at all is a connection hanging
                # rather than refusing, which is exactly what a half-dead proxy
                # does. So the proxy is flagged and the run retries on another.
                error_text = str(exc)
                proxy_failed = True
                hung_sessions += 1
            except asyncio.TimeoutError:
                # Blunt backstop for anything the stall check above could miss -
                # a run that keeps changing steps but never finishes. Same
                # treatment: cancelling resumes the provider coroutine at its
                # suspension point, which runs its own finally: browser.close().
                error_text = (
                    f"session exceeded {SESSION_TIMEOUT_S}s with no result - closed to avoid a "
                    f"frozen browser piling up"
                )
                proxy_failed = True
                hung_sessions += 1
            except Exception as exc:
                # The real exception text goes straight into pipeline_progress
                # (shown on the Pipelines/Monitoring pages) rather than a generic
                # "see server logs" - a step that failed while nobody was
                # watching the terminal used to be undiagnosable from the
                # dashboard alone. This is also where a genuine Chrome-level
                # error (a real net::ERR_* the browser itself reported, as
                # opposed to one of our own now-disabled step timeouts) lands -
                # tuta.py never catches those internally, so they propagate here.
                error_text = f"{type(exc).__name__}: {exc}"
                proxy_failed = _is_proxy_failure(error_text)
                if not proxy_failed:
                    print(f"[identity {identity_id}] email pipeline failed:\n{traceback.format_exc()}")

            # Reached only when the attempt failed (success breaks above).
            if not proxy_failed:
                # Not the proxy's fault - a missing selector, an unexpected
                # page, a rejected username. Burning 24 more proxies on it
                # would just bury the real error under a pile of retries, and
                # the proxy itself is not marked dead: it did its job. (It's
                # still consumed, so it won't be handed to anyone else.)
                proxy_log(f"failed on something other than the proxy, not retrying: {error_text}")
                pipeline_progress.finish(identity_id, error=error_text)
                await _delete_failed_identity(identity_id)
                return

            await flag_proxy_not_working(proxy_id, f"failed in use for identity {identity_id}: {error_text}")

            out_of_attempts = attempt >= MAX_PROXY_ATTEMPTS_PER_RUN
            out_of_time = hung_sessions >= MAX_HUNG_SESSIONS_PER_RUN
            if out_of_attempts or out_of_time:
                reason = (
                    f"{hung_sessions} session(s) hung with no progress"
                    if out_of_time
                    else f"{MAX_PROXY_ATTEMPTS_PER_RUN} proxies all failed in use"
                )
                give_up = f"gave up after {reason} - last error: {error_text}"
                proxy_log(give_up)
                pipeline_progress.finish(identity_id, error=give_up)
                await _delete_failed_identity(identity_id)
                return

            proxy_log(
                f"proxy {proxy_label} failed in use ({error_text}) - flagged it as not working and "
                f"retrying on a different proxy "
                f"({MAX_PROXY_ATTEMPTS_PER_RUN - attempt} attempt(s) left)"
            )

        assert result is not None, "the retry loop must either produce a result or return"
        address = f"{result.username}@{domain}"
        try:
            async with AsyncSessionLocal() as db:
                identity = await db.get(Identity, identity_id)
                if identity is None:
                    pipeline_progress.finish(identity_id, error="identity no longer exists")
                    print(f"[identity {identity_id}] no longer exists, discarding pipeline result")
                    return
                identity.email = address
                identity.email_provider = provider_name.lower()
                identity.email_password = result.password
                await email_service.create_email(
                    db,
                    EmailCreate(
                        type=platform_type,
                        provider_id=platform_id,
                        address=address,
                        password=result.password,
                        used_by_bot_id=None,
                        ever_blocked=False,
                        blocked_on_platforms=[],
                    ),
                )
                await db.commit()
                print(f"[identity {identity_id}] email attached: {identity.email}")
        except Exception:
            # The Tuta account itself WAS created successfully at this point -
            # only saving it locally failed (DB error, etc). Print the
            # credentials so they're not only visible in the traceback, then
            # clean up the now-broken-looking identity same as any other failure.
            pipeline_progress.finish(identity_id, error="mailbox created but saving it to the identity failed - see server logs")
            print(
                f"[identity {identity_id}] failed to attach email after pipeline succeeded "
                f"(address={address}, password={result.password}):\n{traceback.format_exc()}"
            )
            await _delete_failed_identity(identity_id)
            return
    finally:
        manual_gate.clear(identity_id)

    pipeline_progress.finish(identity_id, email=address)


def resume_pipeline(identity_id: UUID) -> bool:
    """Called by POST /api/identities/{id}/pipeline-status/continue, when the
    dashboard's "I solved the CAPTCHA" button is clicked."""
    return manual_gate.resume(identity_id)


def get_pipeline_status_all() -> list[dict]:
    return pipeline_progress.get_all()


def get_pipeline_status(identity_id: UUID) -> Optional[dict]:
    return pipeline_progress.get(identity_id)
