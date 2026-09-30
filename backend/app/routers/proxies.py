from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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
    retired: Optional[bool] = Query(
        None,
        description=(
            "False hides proxies permanently out of circulation (used by a pipeline, or retired "
            "after failing in real use); True shows only those. Their rows are kept so a later "
            "scrape cannot re-import the same address, so they pile up - the Proxies page asks "
            "for retired=false."
        ),
    ),
    provider: Optional[str] = Query(None, description="Only proxies from this provider (Proxy.provider)."),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await proxy_service.get_proxies(
        db, type=type, country=country, is_healthy=is_healthy, assigned=assigned,
        retired=retired, provider=provider,
    )


class ProxyProviderToggle(BaseModel):
    is_enabled: bool


@router.get("/providers")
async def list_proxy_providers(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    """Every proxy source with its on/off state and its share of the pool - what
    the Proxies page groups by."""
    return await proxy_service.get_proxy_providers(db)


@router.patch("/providers/{provider_key}")
async def toggle_proxy_provider(
    provider_key: str,
    body: ProxyProviderToggle,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    """Switches a source on or off for identity generation. Nothing is deleted:
    a disabled provider's proxies stay in the pool and keep showing on the page,
    they just stop being offered to new identities and stop being re-fetched."""
    row = await proxy_service.set_proxy_provider_enabled(db, provider_key, body.is_enabled)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown proxy provider '{provider_key}'")
    return {"key": row.key, "is_enabled": row.is_enabled}


@router.get("/stats")
async def proxy_stats(db: AsyncSession = Depends(get_db), _: str = Depends(get_current_user)):
    """Pool totals, including how many proxies have been retired - counted in
    the database rather than by fetching the rows, since the retired set grows
    without bound by design."""
    return await proxy_service.count_proxies(db)


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
async def test_proxy(
    proxy_id: UUID,
    claim_for: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    proxy = await proxy_service.test_proxy(db, proxy_id, claim_for=claim_for)
    if not proxy:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return proxy
