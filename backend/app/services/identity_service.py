from __future__ import annotations
import random
import string
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.models.identity import Identity, IdentityStatus
from app.models.bot import Bot, BotStatus, BotState
from app.models.email import Email
from app.models.proxy import Proxy
from app.schemas.identity import IdentityCreate, IdentityUpdate
from app.auth.utils import hash_password


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
    existing_email = await db.execute(select(Identity.id).where(Identity.email == data.email))
    if existing_email.scalar_one_or_none() is not None:
        raise ValueError(f"Identity with email '{data.email}' already exists")

    existing_username = await db.execute(select(Identity.id).where(Identity.username == data.username))
    if existing_username.scalar_one_or_none() is not None:
        raise ValueError(f"Identity with username '{data.username}' already exists")

    hashed = hash_password(data.password)
    identity = Identity(**{**data.model_dump(exclude={"password"}), "password_hash": hashed})
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
        email=f"{username}@tempmail.fake",
        email_provider="mail.tm",
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
