from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.schemas.identity import IdentityCreate, IdentityUpdate, IdentityResponse
from app.services import identity_service

router = APIRouter(prefix="/api/identities", tags=["identities"])


@router.get("", response_model=list[IdentityResponse])
async def list_identities(
    status: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await identity_service.get_identities(db, status=status, provider=provider)


@router.post("/generate", response_model=IdentityResponse, status_code=201)
async def generate_identity(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await identity_service.generate_identity(db)


@router.post("", response_model=IdentityResponse, status_code=201)
async def create_identity(data: IdentityCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await identity_service.create_identity(db, data)


@router.get("/{identity_id}", response_model=IdentityResponse)
async def get_identity(identity_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    identity = await identity_service.get_identity(db, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    return identity


@router.patch("/{identity_id}", response_model=IdentityResponse)
async def update_identity(identity_id: UUID, data: IdentityUpdate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    identity = await identity_service.update_identity(db, identity_id, data)
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    return identity


@router.delete("/{identity_id}", status_code=204)
async def delete_identity(identity_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await identity_service.delete_identity(db, identity_id):
        raise HTTPException(status_code=404, detail="Identity not found")
