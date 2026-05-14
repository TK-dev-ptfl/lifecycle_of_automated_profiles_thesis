from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.models.platform import Platform
from app.schemas.platform import PlatformCreate, PlatformUpdate, PlatformResponse

router = APIRouter(prefix="/api/platforms", tags=["platforms"])


@router.get("", response_model=list[PlatformResponse])
async def list_platforms(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    result = await db.execute(select(Platform))
    return result.scalars().all()


@router.post("", response_model=PlatformResponse, status_code=201)
async def create_platform(data: PlatformCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    platform = Platform(**data.model_dump())
    db.add(platform)
    await db.flush()
    await db.refresh(platform)
    return platform


@router.get("/{platform_id}", response_model=PlatformResponse)
async def get_platform(platform_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    result = await db.execute(select(Platform).where(Platform.id == platform_id))
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    return platform


@router.patch("/{platform_id}", response_model=PlatformResponse)
async def update_platform(platform_id: UUID, data: PlatformUpdate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    result = await db.execute(select(Platform).where(Platform.id == platform_id))
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(status_code=404, detail="Platform not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(platform, field, value)
    await db.flush()
    return platform
