"""Live in-memory status of email-creation pipeline runs, keyed by identity.

Process-local by design: a pipeline run lives and dies with the backend
process (same as the BackgroundTasks that drive it - see
identity_service.start_email_pipeline_for_identity), so there is nothing to
persist across restarts. The dashboard's Pipelines page polls
GET /api/identities/pipeline-status, which just returns get_all() below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

_progress: dict[UUID, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start(identity_id: UUID, provider: str, steps: list[dict]) -> None:
    _progress[identity_id] = {
        "identity_id": str(identity_id),
        "provider": provider,
        "status": "running",
        "step_index": -1,
        "step_name": None,
        "manual": False,
        "steps": steps,
        "error": None,
        "started_at": _now(),
        "updated_at": _now(),
    }


def update_step(identity_id: UUID, step_index: int, step_name: str, manual: bool) -> None:
    entry = _progress.get(identity_id)
    if not entry:
        return
    entry["status"] = "waiting_manual" if manual else "running"
    entry["step_index"] = step_index
    entry["step_name"] = step_name
    entry["manual"] = manual
    entry["updated_at"] = _now()


def finish(identity_id: UUID, *, error: Optional[str] = None) -> None:
    entry = _progress.get(identity_id)
    if not entry:
        return
    entry["status"] = "failed" if error else "completed"
    entry["error"] = error
    entry["updated_at"] = _now()


def get(identity_id: UUID) -> Optional[dict]:
    return _progress.get(identity_id)


def get_all() -> list[dict]:
    return list(_progress.values())
