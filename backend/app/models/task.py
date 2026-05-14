from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, func, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class TaskType(str, enum.Enum):
    scrape = "scrape"
    post = "post"
    engage = "engage"
    monitor = "monitor"
    seed = "seed"
    vote = "vote"


class TaskStatus(str, enum.Enum):
    idle = "idle"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class SyncMode(str, enum.Enum):
    independent = "independent"
    sharded = "sharded"
    coordinated = "coordinated"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[TaskType] = mapped_column(SAEnum(TaskType), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.idle)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    sync_mode: Mapped[SyncMode] = mapped_column(SAEnum(SyncMode), default=SyncMode.independent)
    success_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    bots: Mapped[list[Bot]] = relationship("Bot", back_populates="task")
    logs: Mapped[list[Log]] = relationship("Log", back_populates="task")
