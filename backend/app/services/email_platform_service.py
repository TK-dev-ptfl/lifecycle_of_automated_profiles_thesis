from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.email_platform import EmailPlatform
from app.schemas.email_platform import EmailPlatformCreate, EmailPlatformUpdate


async def get_email_platforms(db: AsyncSession, type: Optional[str] = None) -> list[EmailPlatform]:
    q = select(EmailPlatform)
    if type:
        q = q.where(EmailPlatform.type == type)
    result = await db.execute(q.order_by(EmailPlatform.created_at.desc()))
    return result.scalars().all()


async def get_email_platform(db: AsyncSession, platform_id: UUID) -> Optional[EmailPlatform]:
    result = await db.execute(select(EmailPlatform).where(EmailPlatform.id == platform_id))
    return result.scalar_one_or_none()


async def create_email_platform(db: AsyncSession, data: EmailPlatformCreate) -> EmailPlatform:
    item = EmailPlatform(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_email_platform(db: AsyncSession, platform_id: UUID, data: EmailPlatformUpdate) -> Optional[EmailPlatform]:
    item = await get_email_platform(db, platform_id)
    if not item:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    return item


async def delete_email_platform(db: AsyncSession, platform_id: UUID) -> bool:
    item = await get_email_platform(db, platform_id)
    if not item:
        return False
    await db.delete(item)
    return True

