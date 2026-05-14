from __future__ import annotations
import enum
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum as SAEnum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EmailPlatformType(str, enum.Enum):
    temporary = "temporary"
    own_mailserver = "own_mailserver"
    classic = "classic"


class EmailPlatform(Base):
    __tablename__ = "email_platforms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[EmailPlatformType] = mapped_column(SAEnum(EmailPlatformType), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    emails: Mapped[list[Email]] = relationship("Email", back_populates="provider", cascade="all, delete-orphan")

