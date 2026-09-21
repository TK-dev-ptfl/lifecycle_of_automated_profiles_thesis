"""Lets a dashboard button resume a pipeline's manual step (currently just
the CAPTCHA), instead of the pipeline waiting on the backend process's own
terminal stdin - which doesn't exist once the server runs backgrounded, and
previously made the manual step fail with EOFError the instant it was
reached (closing the browser right when it was needed most).

In-process only: the running pipeline coroutine and the API request that
resumes it are both handled by the same asyncio event loop (the FastAPI/
uvicorn process), so a plain asyncio.Event is enough - no queue or DB needed.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

_gates: dict[UUID, asyncio.Event] = {}


def create(identity_id: UUID) -> asyncio.Event:
    event = asyncio.Event()
    _gates[identity_id] = event
    return event


def resume(identity_id: UUID) -> bool:
    """Called by POST /api/identities/{id}/pipeline-status/continue. Returns
    False if no pipeline for this identity is currently waiting (nothing to
    resume, or it already moved past its manual step)."""
    event = _gates.get(identity_id)
    if event is None:
        return False
    event.set()
    return True


def clear(identity_id: UUID) -> None:
    _gates.pop(identity_id, None)
