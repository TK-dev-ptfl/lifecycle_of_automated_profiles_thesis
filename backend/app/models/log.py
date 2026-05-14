from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Enum as SAEnum, Text, func, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class LogLevel(str, enum.Enum):
    info = "info"
    warn = "warn"
    error = "error"
    flag = "flag"


class LogCategory(str, enum.Enum):
    action = "action"
    system = "system"
    network = "network"
    detection = "detection"


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bots.id"), nullable=False)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    level: Mapped[LogLevel] = mapped_column(SAEnum(LogLevel), nullable=False)
    category: Mapped[LogCategory] = mapped_column(SAEnum(LogCategory), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped[Bot] = relationship("Bot", back_populates="logs")
    task: Mapped[Optional[Task]] = relationship("Task", back_populates="logs")
