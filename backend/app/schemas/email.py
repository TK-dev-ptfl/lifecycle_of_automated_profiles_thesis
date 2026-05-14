from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.email_platform import EmailPlatformType


class EmailBase(BaseModel):
    type: EmailPlatformType
    provider_id: UUID
    address: str
    password: Optional[str] = None
    used_by_bot_id: Optional[UUID] = None
    ever_blocked: bool = False
    blocked_on_platforms: list[str] = []


class EmailCreate(EmailBase):
    pass


class EmailUpdate(BaseModel):
    provider_id: Optional[UUID] = None
    address: Optional[str] = None
    password: Optional[str] = None
    used_by_bot_id: Optional[UUID] = None
    ever_blocked: Optional[bool] = None
    blocked_on_platforms: Optional[list[str]] = None


class EmailResponse(EmailBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}

