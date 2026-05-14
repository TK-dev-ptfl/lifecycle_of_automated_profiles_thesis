from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.task import Task, TaskStatus
from app.models.bot import Bot
from app.schemas.task import TaskCreate, TaskUpdate
from datetime import datetime, timezone


async def get_tasks(db: AsyncSession) -> list:
    q = select(Task).options(selectinload(Task.platform), selectinload(Task.bots))
    result = await db.execute(q)
    return result.scalars().all()


async def get_task(db: AsyncSession, task_id: UUID) -> Optional[Task]:
    q = select(Task).where(Task.id == task_id).options(
        selectinload(Task.platform), selectinload(Task.bots)
    )
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def create_task(db: AsyncSession, data: TaskCreate) -> Task:
    task = Task(**data.model_dump())
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def update_task(db: AsyncSession, task_id: UUID, data: TaskUpdate) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    await db.flush()
    return task


async def delete_task(db: AsyncSession, task_id: UUID) -> bool:
    task = await get_task(db, task_id)
    if not task:
        return False
    await db.delete(task)
    return True


async def set_task_status(db: AsyncSession, task_id: UUID, status: TaskStatus) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task:
        return None
    task.status = status
    if status == TaskStatus.running and not task.started_at:
        task.started_at = datetime.now(timezone.utc)
    if status in (TaskStatus.completed, TaskStatus.failed):
        task.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return task


async def assign_bots(db: AsyncSession, task_id: UUID, bot_ids: list) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task:
        return None
    q = select(Bot).where(Bot.id.in_(bot_ids))
    result = await db.execute(q)
    bots = result.scalars().all()
    for bot in bots:
        bot.task_id = task_id
    await db.flush()
    return task


async def unassign_bots(db: AsyncSession, task_id: UUID, bot_ids: list) -> Optional[Task]:
    task = await get_task(db, task_id)
    if not task:
        return None
    q = select(Bot).where(Bot.id.in_(bot_ids), Bot.task_id == task_id)
    result = await db.execute(q)
    bots = result.scalars().all()
    for bot in bots:
        bot.task_id = None
    await db.flush()
    return task


async def get_task_bots(db: AsyncSession, task_id: UUID) -> list:
    q = select(Bot).where(Bot.task_id == task_id)
    result = await db.execute(q)
    return result.scalars().all()
