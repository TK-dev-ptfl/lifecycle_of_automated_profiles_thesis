from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.utils import get_current_user
from app.database import get_db
from app.schemas.email import EmailCreate, EmailResponse, EmailUpdate
from app.services import email_service

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.get("", response_model=list[EmailResponse])
async def list_emails(
    type: Optional[str] = Query(None),
    provider_id: Optional[UUID] = Query(None),
    used_by_bot_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await email_service.get_emails(db, type=type, provider_id=provider_id, used_by_bot_id=used_by_bot_id)


@router.post("", response_model=EmailResponse, status_code=201)
async def create_email(data: EmailCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await email_service.create_email(db, data)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(email_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    item = await email_service.get_email(db, email_id)
    if not item:
        raise HTTPException(status_code=404, detail="Email not found")
    return item


@router.patch("/{email_id}", response_model=EmailResponse)
async def update_email(email_id: UUID, data: EmailUpdate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    item = await email_service.update_email(db, email_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Email not found")
    return item


@router.delete("/{email_id}", status_code=204)
async def delete_email(email_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await email_service.delete_email(db, email_id):
        raise HTTPException(status_code=404, detail="Email not found")

