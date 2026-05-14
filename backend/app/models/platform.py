from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, String, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    api_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    api_secret: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    rate_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    adapter_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bots: Mapped[list[Bot]] = relationship("Bot", back_populates="platform")
    tasks: Mapped[list[Task]] = relationship("Task", back_populates="platform")
