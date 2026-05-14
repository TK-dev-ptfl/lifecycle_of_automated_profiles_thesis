from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.email_platform import EmailPlatformType


class EmailPlatformBase(BaseModel):
    type: EmailPlatformType
    name: str
    domain: str = ""


class EmailPlatformCreate(EmailPlatformBase):
    pass


class EmailPlatformUpdate(BaseModel):
    type: Optional[EmailPlatformType] = None
    name: Optional[str] = None
    domain: Optional[str] = None


class EmailPlatformResponse(EmailPlatformBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
