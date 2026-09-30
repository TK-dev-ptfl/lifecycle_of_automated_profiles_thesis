"""Live in-memory status of email-creation pipeline runs, keyed by identity.

Process-local by design: a pipeline run lives and dies with the backend
process (same as the BackgroundTasks that drive it - see
identity_service.start_email_pipeline_for_identity), so there is nothing to
persist across restarts. The dashboard's Pipelines page polls
GET /api/identities/pipeline-status, which just returns get_all() below; the
Monitoring page's pipeline log viewer polls the same endpoint and reads the
`logs` field.

Entries are self-contained (display_name, proxy, resulting email, and now the
raw log lines all stored here directly) rather than requiring the frontend to
cross-reference the Identity row - a failed pipeline's identity is deleted
(see identity_service._delete_failed_identity), so a live JOIN against
GET /api/identities would lose the failed entry's name/details/messages right
when they're most wanted (see it and understand what broke).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

_progress: dict[UUID, dict] = {}

# Caps memory for a long-running or chatty pipeline - only the most recent
# messages matter for debugging what just happened, and the full history is
# still in the backend's own stdout/terminal scrollback if ever needed.
MAX_LOG_LINES = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def queue(identity_id: UUID, provider: str, display_name: Optional[str] = None) -> None:
    """Records an identity that has been created and handed to the pipeline
    scheduler but is still waiting for one of its slots (see
    app.workers.pipeline_scheduler). Without this, everything between "Generate"
    being clicked and a slot actually opening up is invisible on the
    Pipelines/Monitoring pages - which, with a concurrency cap, can be a while.

    No steps yet: which steps a run has comes from the provider pipeline, and
    start() fills that in when the run actually begins."""
    _progress[identity_id] = {
        "identity_id": str(identity_id),
        "display_name": display_name,
        "provider": provider,
        "status": "queued",
        "step_index": -1,
        "step_name": None,
        "manual": False,
        "steps": [],
        "proxy": None,
        "error": None,
        "email": None,
        "logs": [f"{_now()} queued - waiting for a free pipeline slot"],
        "started_at": _now(),
        "updated_at": _now(),
    }


def start(identity_id: UUID, provider: str, steps: list[dict], display_name: Optional[str] = None) -> None:
    # Carried over from a preceding queue() entry so the wait for a slot stays
    # in the run's own log rather than being wiped the moment it starts.
    existing = _progress.get(identity_id)
    logs = list(existing["logs"]) if existing else []
    _progress[identity_id] = {
        "identity_id": str(identity_id),
        "display_name": display_name,
        "provider": provider,
        "status": "running",
        "step_index": -1,
        "step_name": None,
        "manual": False,
        "steps": steps,
        "proxy": None,
        "error": None,
        "email": None,
        "logs": logs,
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


def set_proxy(identity_id: UUID, proxy_info: Optional[dict]) -> None:
    entry = _progress.get(identity_id)
    if not entry:
        return
    entry["proxy"] = proxy_info
    entry["updated_at"] = _now()


def add_log(identity_id: UUID, message: str) -> None:
    """Appends one raw pipeline message (a Playwright step start/verify line,
    a proxy selection note, an error) - called live as the pipeline runs, not
    just at the end, so the Monitoring page's log viewer reflects what's
    happening right now."""
    entry = _progress.get(identity_id)
    if not entry:
        return
    logs: list[str] = entry["logs"]
    logs.append(f"{_now()} {message}")
    if len(logs) > MAX_LOG_LINES:
        del logs[: len(logs) - MAX_LOG_LINES]
    entry["updated_at"] = _now()


def finish(identity_id: UUID, *, error: Optional[str] = None, email: Optional[str] = None) -> None:
    entry = _progress.get(identity_id)
    if not entry:
        return
    entry["status"] = "failed" if error else "completed"
    entry["error"] = error
    entry["email"] = email
    entry["updated_at"] = _now()


def get(identity_id: UUID) -> Optional[dict]:
    return _progress.get(identity_id)


def get_all() -> list[dict]:
    return list(_progress.values())
