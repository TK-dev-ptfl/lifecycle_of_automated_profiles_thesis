from __future__ import annotations
import asyncio
import random
import string
import traceback
from datetime import datetime, timezone
from typing import Callable, Optional
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


async def _select_and_test_proxy(
    db: AsyncSession,
    identity_id: UUID,
    log: Callable[[str], None] = lambda msg: None,
) -> Optional[Proxy]:
    """If the identity already has a residential/mobile proxy assigned to it
    (the Identities page's own generation flow now live-tests candidates via
    the same "Test" endpoint and assigns one before the identity is even
    created - see selectAndVerifyProxies in the frontend), that's just used
    directly: the freshest-checked assigned one is consumed as-is, with no
    re-test and no pool refresh, since it was already proven alive moments
    ago as part of generation and repeating that work here would only slow
    pipeline start down for nothing.

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

    Only residential and mobile proxies are considered (see ProxyType) -
    datacenter ranges are far more likely to already be flagged by a site's
    anti-abuse heuristics, which is exactly the failure mode observed testing
    this pipeline live. A datacenter proxy already assigned to this identity
    is left alone (still assigned, just not used here) rather than consumed.

    log(message), if given, is called with human-readable notes about what
    happened here (which path was taken, pool-refresh results) - the caller
    wires this to both stdout and pipeline_progress so it's visible on the
    Monitoring page's log viewer, not just the backend's own terminal."""
    ALLOWED_PROXY_TYPES = (ProxyType.residential, ProxyType.mobile)

    assigned = await db.execute(
        select(Proxy)
        .where(
            Proxy.assigned_bot_id == identity_id,
            Proxy.type.in_(ALLOWED_PROXY_TYPES),
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
        refresh = await proxy_service.import_proxies_from_free_list(db)
        if refresh.get("error"):
            log(f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: proxy pool refresh failed: {refresh['error']} - continuing with existing pool")
        else:
            log(
                f"round {round_num}/{MAX_PROXY_SCRAPE_ROUNDS}: refreshed proxy pool: "
                f"{refresh.get('imported', 0)} new, {refresh.get('skipped', 0)} already known"
            )

        # Ordered by last_checked descending (freshest health data first) - a
        # proxy's actual liveness can change within minutes for cheap/public
        # sources, so a check from 5 minutes ago is far more trustworthy than
        # one from 2 days ago, and this order means the still-accurate
        # results get used before the stale ones waste a real test call. No
        # limit - a dead top N one round doesn't mean the rest of the pool
        # is dead too, and giving up early is exactly what mandatory-proxy
        # means not doing.
        free = await db.execute(
            select(Proxy)
            .where(
                Proxy.assigned_bot_id.is_(None),
                Proxy.type.in_(ALLOWED_PROXY_TYPES),
                Proxy.consumed_at.is_(None),
            )
            .order_by(Proxy.is_healthy.desc(), Proxy.last_checked.desc())
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


async def generate_identity(db: AsyncSession) -> Identity:
    names = ["Alex", "Jordan", "Casey", "Morgan", "Taylor", "Riley", "Drew"]
    first = random.choice(names)
    last = _random_str(5).capitalize()
    username = f"{first.lower()}_{last.lower()}_{random.randint(100, 999)}"
    identity = Identity(
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

    def on_step(index: int, step) -> None:
        pipeline_progress.update_step(identity_id, index + 1, step.name, step.manual)

    def on_log(message: str) -> None:
        pipeline_progress.add_log(identity_id, message)

    # Resumed by POST /api/identities/{id}/pipeline-status/continue - not by
    # this process's own stdin, which a backgrounded/nohup'd server doesn't
    # have an interactive one of (input() there raised EOFError immediately,
    # aborting the pipeline and closing the browser right at the CAPTCHA step).
    gate = manual_gate.create(identity_id)

    async def wait_for_manual(prompt: str) -> None:
        await gate.wait()

    def proxy_log(message: str) -> None:
        print(f"[identity {identity_id}] {message}")
        on_log(message)

    try:
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
            error_msg = f"no healthy residential/mobile proxy available after {MAX_PROXY_SCRAPE_ROUNDS} scrape rounds - refusing to run without one"
            proxy_log(error_msg)
            pipeline_progress.set_proxy(identity_id, None)
            pipeline_progress.finish(identity_id, error=error_msg)
            await _delete_failed_identity(identity_id)
            return

        proxy_log(
            f"using proxy {proxy.host}:{proxy.port} "
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

        try:
            result = await provider.run(
                on_step=on_step,
                wait_for_manual=wait_for_manual,
                proxy=proxy_config,
                display_name=display_name,
                age=identity_age,
                on_log=on_log,
            )
        except Exception as exc:
            # The real exception text goes straight into pipeline_progress
            # (shown on the Pipelines/Monitoring pages) rather than a generic
            # "see server logs" - a step that failed while nobody was
            # watching the terminal used to be undiagnosable from the
            # dashboard alone.
            pipeline_progress.finish(identity_id, error=f"{type(exc).__name__}: {exc}")
            print(f"[identity {identity_id}] email pipeline failed:\n{traceback.format_exc()}")
            await _delete_failed_identity(identity_id)
            return

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
