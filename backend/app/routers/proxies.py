from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.schemas.proxy import ProxyCreate, ProxyUpdate, ProxyResponse, ProxyBulkCreate
from app.services import proxy_service

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


@router.get("", response_model=list[ProxyResponse])
async def list_proxies(
    type: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    is_healthy: Optional[bool] = Query(None),
    assigned: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await proxy_service.get_proxies(db, type=type, country=country, is_healthy=is_healthy, assigned=assigned)


@router.post("", response_model=ProxyResponse, status_code=201)
async def create_proxy(data: ProxyCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await proxy_service.create_proxy(db, data)


@router.post("/bulk", response_model=list[ProxyResponse], status_code=201)
async def bulk_create_proxies(data: ProxyBulkCreate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    return await proxy_service.create_proxies_bulk(db, data.proxies)


@router.post("/test-all")
async def test_all_proxies(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    count = await proxy_service.test_all_proxies(db)
    return {"tested": count}


@router.post("/cleanup")
async def cleanup_unhealthy_proxies(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    result = await proxy_service.cleanup_unhealthy_proxies(db)
    return result


@router.post("/fetch-from-free-list")
async def fetch_and_import_proxies(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    """Fetch proxies from free-proxy-list.net and import them into the database."""
    result = await proxy_service.import_proxies_from_free_list(db)
    return result


@router.get("/{proxy_id}", response_model=ProxyResponse)
async def get_proxy(proxy_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    proxy = await proxy_service.get_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return proxy


@router.patch("/{proxy_id}", response_model=ProxyResponse)
async def update_proxy(proxy_id: UUID, data: ProxyUpdate, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    proxy = await proxy_service.update_proxy(db, proxy_id, data)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return proxy


@router.delete("/{proxy_id}", status_code=204)
async def delete_proxy(proxy_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    if not await proxy_service.delete_proxy(db, proxy_id):
        raise HTTPException(status_code=404, detail="Proxy not found")


@router.post("/{proxy_id}/test", response_model=ProxyResponse)
async def test_proxy(proxy_id: UUID, db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    proxy = await proxy_service.test_proxy(db, proxy_id)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return proxy
