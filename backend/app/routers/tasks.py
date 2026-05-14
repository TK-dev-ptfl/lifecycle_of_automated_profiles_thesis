from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse, BotAssignRequest
from app.schemas.bot import BotResponse
from app.services import task_service
from app.models.task import TaskStatus

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await task_service.get_tasks(db)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await task_service.create_task(db, data)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(task_id: UUID, data: TaskUpdate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.update_task(db, task_id, data)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await task_service.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="Task not found")


@router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.set_task_status(db, task_id, TaskStatus.running)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/pause", response_model=TaskResponse)
async def pause_task(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.set_task_status(db, task_id, TaskStatus.paused)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/stop", response_model=TaskResponse)
async def stop_task(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.set_task_status(db, task_id, TaskStatus.failed)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/bots", response_model=list[BotResponse])
async def get_task_bots(task_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await task_service.get_task_bots(db, task_id)


@router.post("/{task_id}/assign", response_model=TaskResponse)
async def assign_bots(task_id: UUID, body: BotAssignRequest, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.assign_bots(db, task_id, body.bot_ids)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/unassign", response_model=TaskResponse)
async def unassign_bots(task_id: UUID, body: BotAssignRequest, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    task = await task_service.unassign_bots(db, task_id, body.bot_ids)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
