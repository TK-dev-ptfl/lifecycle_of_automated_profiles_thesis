from __future__ import annotations
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.email import Email
from app.schemas.email import EmailCreate, EmailUpdate


async def get_emails(
    db: AsyncSession,
    type: Optional[str] = None,
    provider_id: Optional[UUID] = None,
    used_by_bot_id: Optional[UUID] = None,
) -> list[Email]:
    q = select(Email).options(selectinload(Email.provider))
    if type:
        q = q.where(Email.type == type)
    if provider_id:
        q = q.where(Email.provider_id == provider_id)
    if used_by_bot_id:
        q = q.where(Email.used_by_bot_id == used_by_bot_id)
    result = await db.execute(q.order_by(Email.created_at.desc()))
    return result.scalars().all()


async def get_email(db: AsyncSession, email_id: UUID) -> Optional[Email]:
    result = await db.execute(select(Email).where(Email.id == email_id).options(selectinload(Email.provider)))
    return result.scalar_one_or_none()


async def create_email(db: AsyncSession, data: EmailCreate) -> Email:
    item = Email(**data.model_dump())
    db.add(item)
    await db.flush()
    await db.refresh(item)
    return item


async def update_email(db: AsyncSession, email_id: UUID, data: EmailUpdate) -> Optional[Email]:
    item = await get_email(db, email_id)
    if not item:
        return None
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await db.flush()
    await db.refresh(item)
    return item


async def delete_email(db: AsyncSession, email_id: UUID) -> bool:
    item = await get_email(db, email_id)
    if not item:
        return False
    await db.delete(item)
    return True

