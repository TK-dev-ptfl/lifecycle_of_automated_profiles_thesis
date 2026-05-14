from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, func, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class BotMode(str, enum.Enum):
    growing = "growing"
    trust = "trust"
    executing = "executing"
    maintaining = "maintaining"


class BotStatus(str, enum.Enum):
    running = "running"
    paused = "paused"
    stopped = "stopped"
    flagged = "flagged"
    banned = "banned"


class CommunicationMode(str, enum.Enum):
    official_api = "official_api"
    unofficial_api = "unofficial_api"
    scraping = "scraping"
    human_emulation = "human_emulation"


class BehaviourPattern(str, enum.Enum):
    passive = "passive"
    reactive = "reactive"
    proactive = "proactive"
    aggressive = "aggressive"


class BotState(str, enum.Enum):
    in_pipeline = "in_pipeline"
    in_task = "in_task"
    not_active = "not_active"
    blocked = "blocked"


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("platforms.id"), nullable=False)
    identity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("identities.id"), nullable=True)
    identity_value: Mapped[Optional[str]] = mapped_column("identity", String(256), nullable=True)
    profile_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    profile_password: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    platform_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_healthy: Mapped[bool] = mapped_column(default=True)
    sandbox_ids: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[BotState] = mapped_column(SAEnum(BotState), default=BotState.not_active)
    proxy_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("proxies.id", use_alter=True), nullable=True)
    skeleton: Mapped[str] = mapped_column(String(128), default="engagement_farmer")
    mode: Mapped[BotMode] = mapped_column(SAEnum(BotMode), default=BotMode.growing)
    status: Mapped[BotStatus] = mapped_column(SAEnum(BotStatus), default=BotStatus.stopped)
    communication_mode: Mapped[CommunicationMode] = mapped_column(SAEnum(CommunicationMode), default=CommunicationMode.official_api)
    behaviour_pattern: Mapped[BehaviourPattern] = mapped_column(SAEnum(BehaviourPattern), default=BehaviourPattern.passive)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    algorithm_config: Mapped[dict] = mapped_column(JSON, default=dict)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True)
    flag_count: Mapped[int] = mapped_column(Integer, default=0)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    platform: Mapped[Platform] = relationship("Platform", back_populates="bots")
    identity: Mapped[Optional[Identity]] = relationship("Identity", back_populates="bot")
    proxy: Mapped[Optional[Proxy]] = relationship("Proxy", back_populates="bot", foreign_keys="[Proxy.assigned_bot_id]")
    task: Mapped[Optional[Task]] = relationship("Task", back_populates="bots")
    logs: Mapped[list[Log]] = relationship("Log", back_populates="bot")
