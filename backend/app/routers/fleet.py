from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.models.bot import Bot, BotStatus, BotMode
from app.models.platform import Platform

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/summary")
async def fleet_summary(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    total = await db.execute(select(func.count()).select_from(Bot))
    by_status = {}
    for s in BotStatus:
        cnt = await db.execute(select(func.count()).select_from(Bot).where(Bot.status == s))
        by_status[s.value] = cnt.scalar()
    by_mode = {}
    for m in BotMode:
        cnt = await db.execute(select(func.count()).select_from(Bot).where(Bot.mode == m))
        by_mode[m.value] = cnt.scalar()
    return {
        "total": total.scalar(),
        "by_status": by_status,
        "by_mode": by_mode,
    }


@router.get("/health")
async def fleet_health(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    result = await db.execute(select(Bot))
    bots = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "name": b.name,
            "status": b.status.value,
            "mode": b.mode.value,
            "flag_count": b.flag_count,
            "last_active": b.last_active.isoformat() if b.last_active else None,
        }
        for b in bots
    ]
