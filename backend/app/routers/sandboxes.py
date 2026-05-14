from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.utils import get_current_user
from app.database import get_db
from app.schemas.sandbox import SandboxCreate, SandboxResponse, SandboxUpdate
from app.services import sandbox_service

router = APIRouter(prefix="/api/sandboxes", tags=["sandboxes"])


@router.get("", response_model=list[SandboxResponse])
async def list_sandboxes(
    groupname: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await sandbox_service.get_sandboxes(db, groupname=groupname)


@router.post("", response_model=SandboxResponse, status_code=201)
async def create_sandbox(data: SandboxCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await sandbox_service.create_sandbox(db, data)


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    item = await sandbox_service.get_sandbox(db, sandbox_id)
    if not item:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return item


@router.patch("/{sandbox_id}", response_model=SandboxResponse)
async def update_sandbox(
    sandbox_id: UUID,
    data: SandboxUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    item = await sandbox_service.update_sandbox(db, sandbox_id, data)
    if not item:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return item


@router.delete("/{sandbox_id}", status_code=204)
async def delete_sandbox(sandbox_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await sandbox_service.delete_sandbox(db, sandbox_id):
        raise HTTPException(status_code=404, detail="Sandbox not found")

