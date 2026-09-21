from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from app.models.identity import IdentityStatus


class IdentityBase(BaseModel):
    display_name: str
    username: str
    email: Optional[str] = None
    email_provider: Optional[str] = None
    email_password: Optional[str] = None
    phone_number: Optional[str] = None
    phone_provider: Optional[str] = None
    profile_photo_url: Optional[str] = None
    bio: Optional[str] = None
    location: str
    age: int
    interests: list = []
    browser_profile_id: str = ""
    browser_profile_provider: str = ""


class IdentityCreate(IdentityBase):
    password: str
    # Which EmailPlatform to create a mailbox with, when email is omitted.
    # Not a column on Identity itself - only used to pick the pipeline to run.
    email_platform_id: Optional[UUID] = None


class GenerateIdentityRequest(BaseModel):
    email_platform_id: Optional[UUID] = None


class IdentityUpdate(BaseModel):
    display_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    status: Optional[IdentityStatus] = None
    phone_number: Optional[str] = None
    interests: Optional[list] = None
    email: Optional[str] = None
    email_provider: Optional[str] = None
    email_password: Optional[str] = None


class IdentityResponse(IdentityBase):
    id: UUID
    status: IdentityStatus
    created_at: datetime

    model_config = {"from_attributes": True}
