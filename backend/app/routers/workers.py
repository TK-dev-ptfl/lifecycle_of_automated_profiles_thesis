from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.utils import get_current_user
from app.workers import WORKERS
from app.workers.pipeline_scheduler import pipeline_scheduler
from app.workers.proxy_refresher import proxy_refresher

router = APIRouter(prefix="/api/workers", tags=["workers"])


class SchedulerConfig(BaseModel):
    """Optional overrides applied before the scheduler starts. All of them
    persist across a later stop/start, so a restart doesn't silently fall back
    to the defaults."""

    concurrency: Optional[int] = Field(default=None, ge=1, le=50)
    email_platform_id: Optional[UUID] = None
    # False (the default): the scheduler only runs what's been handed to it -
    # creating identities is what fills the queue. True: it also generates its
    # own identities whenever the queue runs dry, so `concurrency` pipelines are
    # always running rather than only on demand.
    continuous: Optional[bool] = None


@router.get("")
async def list_workers(_: str = Depends(get_current_user)):
    return [worker.status() for worker in WORKERS.values()]


@router.get("/{worker_name}")
async def get_worker(worker_name: str, _: str = Depends(get_current_user)):
    worker = WORKERS.get(worker_name)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Unknown worker (known: {', '.join(sorted(WORKERS))})")
    return worker.status()


@router.post("/proxy-refresher/start")
async def start_proxy_refresher(_: str = Depends(get_current_user)):
    started = proxy_refresher.start()
    return {"started": started, "status": proxy_refresher.status()}


@router.post("/proxy-refresher/stop")
async def stop_proxy_refresher(_: str = Depends(get_current_user)):
    stopped = await proxy_refresher.stop()
    return {"stopped": stopped, "status": proxy_refresher.status()}


@router.post("/pipeline-scheduler/start")
async def start_pipeline_scheduler(
    config: SchedulerConfig | None = None,
    _: str = Depends(get_current_user),
):
    """Starts the scheduler loop. Normally there's no need to call this -
    creating an identity that needs a mailbox queues it and starts the worker on
    its own. Call it to change the concurrency cap, or to turn on continuous
    mode, where the worker generates its own identities to keep every slot busy
    instead of waiting to be asked.

    Continuous mode is explicit rather than automatic on boot for the obvious
    reason: each slot it fills launches a real Chromium instance and registers a
    real mailbox, which shouldn't begin just because the server restarted."""
    if config is not None:
        pipeline_scheduler.configure(
            concurrency=config.concurrency,
            email_platform_id=config.email_platform_id,
            continuous=config.continuous,
        )
    if pipeline_scheduler.continuous and pipeline_scheduler.email_platform_id is None:
        # Continuous mode invents its own jobs, so unlike a queued one there's
        # no requester to say which platform they're for.
        default_id = await pipeline_scheduler.default_platform_id()
        if default_id is None:
            raise HTTPException(
                status_code=422,
                detail="Continuous mode needs an email platform with an automated signup pipeline - none is configured",
            )
        pipeline_scheduler.configure(email_platform_id=default_id)
    started = pipeline_scheduler.start()
    return {"started": started, "status": pipeline_scheduler.status()}


@router.post("/pipeline-scheduler/stop")
async def stop_pipeline_scheduler(_: str = Depends(get_current_user)):
    """Stops the supervisor and cancels the in-flight pipelines with it - see
    PipelineScheduler.stop, which closes their browsers rather than orphaning
    them.

    Continuous mode is switched off here too. Without that, the next identity
    anyone creates would restart the worker (queueing starts it on demand) and
    it would go straight back to generating its own identities forever - the
    opposite of what pressing Stop means. Jobs already queued are kept; clear
    them with DELETE /api/identities/pipeline-queue."""
    pipeline_scheduler.configure(continuous=False)
    stopped = await pipeline_scheduler.stop()
    return {"stopped": stopped, "status": pipeline_scheduler.status()}
