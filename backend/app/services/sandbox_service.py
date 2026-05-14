from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sandbox import Sandbox
from app.schemas.sandbox import SandboxCreate, SandboxUpdate


async def get_sandboxes(db: AsyncSession, groupname: Optional[str] = None) -> list[Sandbox]:
    q = select(Sandbox)
    if groupname:
        q = q.where(Sandbox.groupname == groupname)
    result = await db.execute(q.order_by(Sandbox.created_at.desc()))
    return result.scalars().all()


async def get_sandbox(db: AsyncSession, sandbox_id: UUID) -> Optional[Sandbox]:
    result = await db.execute(select(Sandbox).where(Sandbox.id == sandbox_id))
    return result.scalar_one_or_none()


async def create_sandbox(db: AsyncSession, data: SandboxCreate) -> Sandbox:
    item = Sandbox(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_sandbox(db: AsyncSession, sandbox_id: UUID, data: SandboxUpdate) -> Optional[Sandbox]:
    item = await get_sandbox(db, sandbox_id)
    if not item:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    return item


async def delete_sandbox(db: AsyncSession, sandbox_id: UUID) -> bool:
    item = await get_sandbox(db, sandbox_id)
    if not item:
        return False
    await db.delete(item)
    return True

