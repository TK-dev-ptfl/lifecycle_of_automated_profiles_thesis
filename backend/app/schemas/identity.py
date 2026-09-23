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
    # Lets the caller decide the identity's id up front, before it exists,
    # instead of always getting a server-generated one back. The Identities
    # page's generation flow does this specifically so a proxy can be
    # atomically claimed (see POST /api/proxies/{id}/test's claim_for) for
    # this exact id the moment it's confirmed alive - *before* this endpoint
    # is even called - closing a race where a different, already-running
    # pipeline's own free-pool search could otherwise grab the same proxy
    # first. Falls back to a server-generated UUID (the previous, only
    # behavior) when omitted.
    id: Optional[UUID] = None
    # Which EmailPlatform to create a mailbox with, when email is omitted.
    # Not a column on Identity itself - only used to pick the pipeline to run.
    email_platform_id: Optional[UUID] = None
    # A proxy already live-tested and reserved for this identity by the
    # caller. Not a column on Identity itself - identity_service.create_identity
    # claims it atomically (assigned_bot_id) in the same request that
    # creates the identity, so it's guaranteed to be in place *before* the
    # background pipeline task is ever scheduled. Superseded for the
    # Identities page's own flow by claim_for above (which claims earlier
    # still, during the proxy test itself) but kept as a fallback for any
    # other caller that supplies a proxy without having pre-claimed it.
    proxy_id: Optional[UUID] = None


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
