from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.email_platform import EmailPlatformType


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[EmailPlatformType] = mapped_column(SAEnum(EmailPlatformType), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("email_platforms.id"), nullable=False)
    address: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    password: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    used_by_bot_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("bots.id"), nullable=True)
    ever_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_on_platforms: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    provider: Mapped[EmailPlatform] = relationship("EmailPlatform", back_populates="emails")
    used_by_bot: Mapped[Optional[Bot]] = relationship("Bot")
