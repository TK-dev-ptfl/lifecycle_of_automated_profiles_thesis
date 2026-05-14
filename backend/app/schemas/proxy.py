from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.proxy import ProxyProtocol, ProxyType


class ProxyBase(BaseModel):
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: ProxyProtocol = ProxyProtocol.http
    type: ProxyType = ProxyType.datacenter
    country: str
    city: Optional[str] = None
    provider: str


class ProxyCreate(ProxyBase):
    pass


class ProxyUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    is_healthy: Optional[bool] = None
    country: Optional[str] = None
    city: Optional[str] = None


class ProxyResponse(ProxyBase):
    id: UUID
    assigned_bot_id: Optional[UUID]
    is_healthy: bool
    last_checked: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ProxyBulkCreate(BaseModel):
    proxies: list[ProxyCreate]
