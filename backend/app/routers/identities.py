from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.auth.utils import get_current_user
from app.pipelines.email_pool.registry import PROVIDER_PIPELINES
from app.schemas.identity import GenerateIdentityRequest, IdentityCreate, IdentityUpdate, IdentityResponse
from app.services import email_platform_service, identity_service
from app.workers.pipeline_scheduler import pipeline_scheduler

router = APIRouter(prefix="/api/identities", tags=["identities"])


async def _resolve_email_platform(db: AsyncSession, email_platform_id: Optional[UUID]):
    """Validated before any identity row is written, so a bad/missing
    platform id fails clean with no orphaned identity left behind."""
    if email_platform_id is None:
        raise HTTPException(status_code=422, detail="email_platform_id is required to create a mailbox")
    platform = await email_platform_service.get_email_platform(db, email_platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail="Email platform not found")
    if platform.name.strip().lower() not in PROVIDER_PIPELINES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{platform.name}' has no automated signup pipeline yet "
                f"(available: {', '.join(sorted(PROVIDER_PIPELINES))})"
            ),
        )
    return platform


def _queue_pipeline(identity, platform) -> None:
    """Hands a freshly created identity to the pipeline scheduler.

    Queued rather than started here: the scheduler caps how many signup
    pipelines run at once (each is a full Chromium instance), so creating 20
    identities is 20 instant rows plus a queue, not 20 browsers. It also means
    the request returns immediately - it never waits on a proxy search.
    Previously this was a FastAPI BackgroundTask per identity, which started
    every pipeline at once with no cap at all."""
    pipeline_scheduler.enqueue(
        identity.id,
        platform.id,
        display_name=identity.display_name,
        provider_name=platform.name,
    )


@router.get("", response_model=list[IdentityResponse])
async def list_identities(
    status: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    return await identity_service.get_identities(db, status=status, provider=provider)


@router.get("/pipeline-status")
async def list_pipeline_status(_: str = Depends(get_current_user)):
    return identity_service.get_pipeline_status_all()


@router.get("/{identity_id}/pipeline-status")
async def get_pipeline_status(identity_id: UUID, _: str = Depends(get_current_user)):
    status = identity_service.get_pipeline_status(identity_id)
    if status is None:
        raise HTTPException(status_code=404, detail="No pipeline run for this identity")
    return status


@router.post("/{identity_id}/pipeline-status/continue")
async def continue_pipeline(identity_id: UUID, _: str = Depends(get_current_user)):
    """Resumes a pipeline paused on its manual step (the CAPTCHA) - click
    target for the dashboard's "I solved the CAPTCHA" button."""
    if not identity_service.resume_pipeline(identity_id):
        raise HTTPException(status_code=404, detail="No pipeline is currently waiting for this identity")
    return {"ok": True}


@router.post("/generate", response_model=IdentityResponse, status_code=201)
async def generate_identity(
    body: GenerateIdentityRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    platform = await _resolve_email_platform(db, body.email_platform_id)
    identity = await identity_service.generate_identity(db)
    # Generated without an email; the scheduler assigns it a proxy and runs the
    # signup pipeline when a slot frees up, then attaches the mailbox.
    await db.commit()
    _queue_pipeline(identity, platform)
    return identity


@router.post("", response_model=IdentityResponse, status_code=201)
async def create_identity(
    data: IdentityCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    platform = None
    if data.email is None:
        platform = await _resolve_email_platform(db, data.email_platform_id)
    try:
        identity = await identity_service.create_identity(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if platform is not None:
        # Committed before queueing: the scheduler opens its own session and
        # looks the identity up by id, so the row has to be visible to it
        # (get_db would otherwise not commit until after this handler returns).
        await db.commit()
        _queue_pipeline(identity, platform)
    return identity


@router.get("/pipeline-queue")
async def get_pipeline_queue(_: str = Depends(get_current_user)):
    """What the pipeline scheduler is doing with the identities handed to it -
    how many are queued, how many are running, and the cap."""
    status = pipeline_scheduler.status()
    return {
        "running": status["running"],
        "queued": status["queued"],
        "active_slots": status["active_slots"],
        "concurrency": status["concurrency"],
        "continuous": status["continuous"],
        "launched": status["launched"],
    }


@router.delete("/pipeline-queue")
async def clear_pipeline_queue(_: str = Depends(get_current_user)):
    """Drops everything not yet started. In-flight pipelines keep running -
    stop those via POST /api/workers/pipeline-scheduler/stop."""
    return {"dropped": pipeline_scheduler.clear_queue()}


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
