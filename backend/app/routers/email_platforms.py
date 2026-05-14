from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.utils import get_current_user
from app.database import get_db
from app.schemas.email_platform import EmailPlatformCreate, EmailPlatformResponse, EmailPlatformUpdate
from app.services import email_platform_service

router = APIRouter(prefix="/api/email-platforms", tags=["email-platforms"])


@router.get("", response_model=list[EmailPlatformResponse])
async def list_email_platforms(
    type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await email_platform_service.get_email_platforms(db, type=type)


@router.post("", response_model=EmailPlatformResponse, status_code=201)
async def create_email_platform(
    data: EmailPlatformCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await email_platform_service.create_email_platform(db, data)


@router.get("/{platform_id}", response_model=EmailPlatformResponse)
async def get_email_platform(platform_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    item = await email_platform_service.get_email_platform(db, platform_id)
    if not item:
        raise HTTPException(status_code=404, detail="Email platform not found")
    return item


@router.patch("/{platform_id}", response_model=EmailPlatformResponse)
async def update_email_platform(
    platform_id: UUID,
    data: EmailPlatformUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    item = await email_platform_service.update_email_platform(db, platform_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Email platform not found")
    return item


@router.delete("/{platform_id}", status_code=204)
async def delete_email_platform(platform_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await email_platform_service.delete_email_platform(db, platform_id):
        raise HTTPException(status_code=404, detail="Email platform not found")

