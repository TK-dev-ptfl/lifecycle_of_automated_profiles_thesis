from __future__ import annotations
import asyncio
import random
import string
import traceback
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.database import AsyncSessionLocal
from app.models.email_platform import EmailPlatformType
from app.models.identity import Identity, IdentityStatus
from app.models.bot import Bot, BotStatus, BotState
from app.models.email import Email
from app.models.proxy import Proxy
from app.schemas.email import EmailCreate
from app.schemas.identity import IdentityCreate, IdentityUpdate
from app.auth.utils import hash_password
from app.services import email_service
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
# Pools imported from free-proxy-list-style sources are mostly dead; testing
# every one at up to 10s/timeout each could take the better part of an hour.
# Try known-good/most-recently-checked ones first and cap how many we bother
# with - if none of those pan out we proceed unproxied rather than block
# identity creation on a bad pool (see _select_and_test_proxy's return None).
MAX_PROXY_CANDIDATES = 15


async def _test_and_consume_assigned_proxy(db: AsyncSession, proxy: Proxy) -> bool:
    """For a proxy already exclusively tied to this identity - no other
    concurrent pipeline can claim it, so a plain test-then-delete is enough
    (no atomic guard needed, unlike the free-pool path below)."""
    healthy = await asyncio.to_thread(check_proxy_health, proxy.host, proxy.port, proxy.protocol.value)
    if not healthy:
        proxy.is_healthy = False
        proxy.last_checked = datetime.now(timezone.utc)
        await db.commit()
        return False
    await db.delete(proxy)
    await db.commit()
    return True


async def _claim_and_consume_free_proxy(db: AsyncSession, proxy_id: UUID, identity_id: UUID) -> bool:
    """Atomically removes this proxy from the free pool - concurrent
    pipelines run without any process-wide lock now, so two identities could
    otherwise both see the same 'free' proxy as a candidate at the same time
    and both try to use it. DELETE ... WHERE assigned_bot_id IS NULL is the
    guard: whichever caller's statement actually deletes the row (rowcount
    == 1) won the claim; the loser sees rowcount == 0 and moves on to its
    next candidate instead of double-using the same IP for two accounts."""
    result = await db.execute(
        sa_delete(Proxy).where(Proxy.id == proxy_id, Proxy.assigned_bot_id.is_(None))
    )
    await db.commit()
    return result.rowcount == 1


async def _select_and_test_proxy(db: AsyncSession, identity_id: UUID) -> Optional[Proxy]:
    """Prefers a proxy already assigned to this identity (e.g. by the
    Identities page's country-based selection when it was generated);
    otherwise picks from the pool, previously-healthy and recently-checked
    ones first. Either way it's re-tested with the same tool the Proxies
    page's own "Test" button uses (check_proxy_health) before being trusted
    for the signup, and then consumed - removed from the pool entirely - so
    it can never be reused for a second identity/account. Returns None if
    nothing in the (capped) candidate list is healthy; caller falls back to
    running unproxied rather than blocking identity creation on a bad pool."""
    assigned = await db.execute(select(Proxy).where(Proxy.assigned_bot_id == identity_id))
    for proxy in assigned.scalars().all():
        if await _test_and_consume_assigned_proxy(db, proxy):
            return proxy

    free = await db.execute(
        select(Proxy)
        .where(Proxy.assigned_bot_id.is_(None))
        .order_by(Proxy.is_healthy.desc(), Proxy.last_checked.desc())
        .limit(MAX_PROXY_CANDIDATES)
    )
    for proxy in free.scalars().all():
        healthy = await asyncio.to_thread(check_proxy_health, proxy.host, proxy.port, proxy.protocol.value)
        if not healthy:
            proxy.is_healthy = False
            proxy.last_checked = datetime.now(timezone.utc)
            await db.commit()
            continue
        if await _claim_and_consume_free_proxy(db, proxy.id, identity_id):
            return proxy
        # Someone else's concurrent pipeline claimed it first - try the next.

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
    identity = Identity(
        **{**data.model_dump(exclude={"password", "email_platform_id"}), "password_hash": hashed}
    )
    db.add(identity)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("Identity with the same email or username already exists")
    await db.refresh(identity)
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

        # Release proxy assignment by both relation pointers.
        if bot.proxy_id:
            proxy = await db.get(Proxy, bot.proxy_id)
            if proxy:
                proxy.assigned_bot_id = None
            bot.proxy_id = None
        proxy_by_bot_result = await db.execute(select(Proxy).where(Proxy.assigned_bot_id == bot.id))
        proxies = proxy_by_bot_result.scalars().all()
        for proxy in proxies:
            proxy.assigned_bot_id = None

        # Detach bot from identity and reset lifecycle state.
        bot.identity_id = None
        bot.state = BotState.not_active
        bot.status = BotStatus.stopped

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
    bot later. Live progress is tracked in app.pipelines.email_pool.progress
    for the dashboard's Pipelines page (GET /api/identities/pipeline-status)
    to poll.

    Fire-and-forget: intended to be scheduled via FastAPI's BackgroundTasks
    right after the identity is created/generated, so the HTTP response
    doesn't wait on a multi-minute, human-in-the-loop browser pipeline. Opens
    its own DB session since the request-scoped one will already be closed by
    the time this finishes.
    """
    try:
        provider = get_provider_pipeline(provider_name)
    except ValueError as exc:
        pipeline_progress.start(identity_id, provider_name, [])
        pipeline_progress.finish(identity_id, error=str(exc))
        print(f"[identity {identity_id}] {exc}")
        return

    # select_and_test_proxy runs before any of the provider's own steps -
    # index 0 is reserved for it, so on_step below shifts the provider's
    # indices up by one to make room.
    steps = [{"name": PROXY_STEP_NAME, "manual": False}] + provider.describe()
    pipeline_progress.start(identity_id, provider_name, steps)

    def on_step(index: int, step) -> None:
        pipeline_progress.update_step(identity_id, index + 1, step.name, step.manual)

    # Resumed by POST /api/identities/{id}/pipeline-status/continue - not by
    # this process's own stdin, which a backgrounded/nohup'd server doesn't
    # have an interactive one of (input() there raised EOFError immediately,
    # aborting the pipeline and closing the browser right at the CAPTCHA step).
    gate = manual_gate.create(identity_id)

    async def wait_for_manual(prompt: str) -> None:
        await gate.wait()

    try:
        pipeline_progress.update_step(identity_id, 0, PROXY_STEP_NAME, False)
        async with AsyncSessionLocal() as db:
            identity_for_name = await db.get(Identity, identity_id)
            display_name = identity_for_name.display_name if identity_for_name else None
            proxy = await _select_and_test_proxy(db, identity_id)

        if proxy is None:
            # A missing/entirely-dead pool shouldn't block account
            # creation - proceed unproxied (from the backend's own IP)
            # rather than fail the whole signup over it.
            print(f"[identity {identity_id}] no healthy proxy found (checked up to {MAX_PROXY_CANDIDATES}), continuing without one")
            proxy_config = None
        else:
            print(
                f"[identity {identity_id}] using proxy {proxy.host}:{proxy.port} "
                f"(type={proxy.type.value}, protocol={proxy.protocol.value}, country={proxy.country}) "
                f"- removed from the pool, will not be reused"
            )
            proxy_config = _proxy_to_playwright_config(proxy)

        try:
            result = await provider.run(
                on_step=on_step,
                wait_for_manual=wait_for_manual,
                proxy=proxy_config,
                display_name=display_name,
            )
        except Exception:
            pipeline_progress.finish(identity_id, error="pipeline failed - see server logs")
            print(f"[identity {identity_id}] email pipeline failed:\n{traceback.format_exc()}")
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
            # Mailbox was created successfully but saving it failed (DB
            # error, bad id, etc.) - record that clearly instead of an
            # uncaught exception leaving the dashboard stuck on "running".
            pipeline_progress.finish(identity_id, error="mailbox created but saving it to the identity failed - see server logs")
            print(f"[identity {identity_id}] failed to attach email after pipeline succeeded:\n{traceback.format_exc()}")
            return
    finally:
        manual_gate.clear(identity_id)

    pipeline_progress.finish(identity_id)


def resume_pipeline(identity_id: UUID) -> bool:
    """Called by POST /api/identities/{id}/pipeline-status/continue, when the
    dashboard's "I solved the CAPTCHA" button is clicked."""
    return manual_gate.resume(identity_id)


def get_pipeline_status_all() -> list[dict]:
    return pipeline_progress.get_all()


def get_pipeline_status(identity_id: UUID) -> Optional[dict]:
    return pipeline_progress.get(identity_id)
