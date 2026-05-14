from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.task import TaskType, TaskStatus, SyncMode


class TaskBase(BaseModel):
    name: str
    platform_id: UUID
    type: TaskType
    payload: dict = {}
    schedule: dict = {}
    concurrency: int = 1
    sync_mode: SyncMode = SyncMode.independent
    success_criteria: dict = {}


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    payload: Optional[dict] = None
    schedule: Optional[dict] = None
    concurrency: Optional[int] = None
    sync_mode: Optional[SyncMode] = None
    success_criteria: Optional[dict] = None


class TaskResponse(TaskBase):
    id: UUID
    status: TaskStatus
    result_count: int
    error_count: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class BotAssignRequest(BaseModel):
    bot_ids: list[UUID]
