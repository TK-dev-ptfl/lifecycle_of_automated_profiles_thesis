from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class SandboxBase(BaseModel):
    groupname: str
    name: str
    password: str


class SandboxCreate(SandboxBase):
    pass


class SandboxUpdate(BaseModel):
    groupname: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None


class SandboxResponse(SandboxBase):
    id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
