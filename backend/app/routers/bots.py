from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.schemas.bot import BotCreate, BotUpdate, BotResponse, BotSetModeRequest, BotStatsResponse, LogResponse
from app.services import bot_service
from app.models.bot import BotStatus

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("", response_model=list[BotResponse])
async def list_bots(
    status: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    task_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await bot_service.get_bots(db, status=status, mode=mode, task_id=task_id)


@router.post("", response_model=BotResponse, status_code=201)
async def create_bot(
    data: BotCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await bot_service.create_bot(db, data)


@router.get("/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    bot = await bot_service.get_bot(db, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.patch("/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: UUID, data: BotUpdate,
    db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user),
):
    bot = await bot_service.update_bot(db, bot_id, data)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.delete("/{bot_id}", status_code=204)
async def delete_bot(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await bot_service.delete_bot(db, bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")


@router.post("/{bot_id}/run", response_model=BotResponse)
async def run_bot(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    bot = await bot_service.set_bot_status(db, bot_id, BotStatus.running)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.post("/{bot_id}/pause", response_model=BotResponse)
async def pause_bot(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    bot = await bot_service.set_bot_status(db, bot_id, BotStatus.paused)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.post("/{bot_id}/stop", response_model=BotResponse)
async def stop_bot(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    bot = await bot_service.set_bot_status(db, bot_id, BotStatus.stopped)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.post("/{bot_id}/set-mode", response_model=BotResponse)
async def set_mode(
    bot_id: UUID, body: BotSetModeRequest,
    db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user),
):
    bot = await bot_service.set_bot_mode(db, bot_id, body.mode)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot


@router.get("/{bot_id}/logs", response_model=list)
async def get_bot_logs(
    bot_id: UUID,
    skip: int = Query(0), limit: int = Query(50),
    db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user),
):
    return await bot_service.get_bot_logs(db, bot_id, skip=skip, limit=limit)


@router.get("/{bot_id}/stats", response_model=BotStatsResponse)
async def get_bot_stats(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await bot_service.get_bot_stats(db, bot_id)


@router.get("/{bot_id}/flags", response_model=list)
async def get_bot_flags(bot_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await bot_service.get_bot_flags(db, bot_id)
