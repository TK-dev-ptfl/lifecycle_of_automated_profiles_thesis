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
    # Set once this proxy has been handed to a pipeline, or retired after
    # failing in real use - permanent, and what excludes it from every
    # candidate search. Exposed so the Proxies page can tell "free" from
    # "reserved" from "retired" rather than showing all three as "assigned".
    consumed_at: Optional[datetime] = None
    # One endpoint, a different exit IP per connection - so it is never retired
    # after a single use. The Proxies page badges these, since "used 0 times,
    # still available" would otherwise look like a bug.
    is_rotating: bool = False
    last_checked: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ProxyBulkCreate(BaseModel):
    proxies: list[ProxyCreate]
