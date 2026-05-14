from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel


class PlatformBase(BaseModel):
    name: str
    display_name: str
    is_enabled: bool = True
    rate_limits: dict = {}
    adapter_config: dict = {}


class PlatformCreate(PlatformBase):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None


class PlatformUpdate(BaseModel):
    display_name: Optional[str] = None
    is_enabled: Optional[bool] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    rate_limits: Optional[dict] = None
    adapter_config: Optional[dict] = None


class PlatformResponse(PlatformBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
