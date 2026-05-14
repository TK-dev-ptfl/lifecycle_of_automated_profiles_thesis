from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class IdentityStatus(str, enum.Enum):
    fresh = "fresh"
    active = "active"
    flagged = "flagged"
    burned = "burned"


class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    email_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    email_password: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    phone_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    profile_photo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    interests: Mapped[list] = mapped_column(JSON, default=list)
    browser_profile_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    browser_profile_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[IdentityStatus] = mapped_column(SAEnum(IdentityStatus), default=IdentityStatus.fresh)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped[Optional[Bot]] = relationship("Bot", back_populates="identity", uselist=False)
