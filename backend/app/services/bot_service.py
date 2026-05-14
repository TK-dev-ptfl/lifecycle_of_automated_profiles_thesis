from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.bot import Bot, BotStatus, BotMode
from app.models.log import Log, LogLevel, LogCategory
from app.schemas.bot import BotCreate, BotUpdate


async def get_bots(
    db: AsyncSession,
    status: Optional[str] = None,
    mode: Optional[str] = None,
    platform_id: Optional[UUID] = None,
    task_id: Optional[UUID] = None,
) -> list:
    q = select(Bot).options(selectinload(Bot.platform), selectinload(Bot.identity), selectinload(Bot.proxy))
    if status:
        q = q.where(Bot.status == status)
    if mode:
        q = q.where(Bot.mode == mode)
    if platform_id:
        q = q.where(Bot.platform_id == platform_id)
    if task_id:
        q = q.where(Bot.task_id == task_id)
    result = await db.execute(q)
    return result.scalars().all()


async def get_bot(db: AsyncSession, bot_id: UUID) -> Optional[Bot]:
    q = select(Bot).where(Bot.id == bot_id).options(
        selectinload(Bot.platform), selectinload(Bot.identity), selectinload(Bot.proxy)
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def create_bot(db: AsyncSession, data: BotCreate) -> Bot:
    bot = Bot(**data.model_dump())
    db.add(bot)
    await db.flush()
    await db.refresh(bot)
    return bot


async def update_bot(db: AsyncSession, bot_id: UUID, data: BotUpdate) -> Optional[Bot]:
    bot = await get_bot(db, bot_id)
    if not bot:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(bot, field, value)
    await db.flush()
    await db.refresh(bot)
    return bot


async def delete_bot(db: AsyncSession, bot_id: UUID) -> bool:
    bot = await get_bot(db, bot_id)
    if not bot:
        return False
    await db.delete(bot)
    return True


async def set_bot_status(db: AsyncSession, bot_id: UUID, status: BotStatus) -> Optional[Bot]:
    bot = await get_bot(db, bot_id)
    if not bot:
        return None
    bot.status = status
    await db.flush()
    await db.refresh(bot)
    return bot


async def set_bot_mode(db: AsyncSession, bot_id: UUID, mode: BotMode) -> Optional[Bot]:
    bot = await get_bot(db, bot_id)
    if not bot:
        return None
    bot.mode = mode
    await db.flush()
    await db.refresh(bot)
    return bot


async def get_bot_logs(db: AsyncSession, bot_id: UUID, skip: int = 0, limit: int = 50) -> list:
    q = select(Log).where(Log.bot_id == bot_id).order_by(Log.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def get_bot_stats(db: AsyncSession, bot_id: UUID) -> dict:
    result = await db.execute(select(func.count()).where(Log.bot_id == bot_id))
    log_count = result.scalar() or 0
    bot = await get_bot(db, bot_id)
    return {
        "actions_today": log_count,
        "actions_lifetime": log_count,
        "success_rate": 0.95,
        "uptime_hours": 24.0,
        "flag_count": bot.flag_count if bot else 0,
    }


async def get_bot_flags(db: AsyncSession, bot_id: UUID) -> list:
    q = select(Log).where(Log.bot_id == bot_id, Log.level == LogLevel.flag).order_by(Log.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()
