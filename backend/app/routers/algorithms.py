from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.utils import get_current_user
from app.services import behaviour_run_service

router = APIRouter(prefix="/api/algorithms", tags=["algorithms"])

METHODS_ROOT = Path(__file__).resolve().parent.parent / "algorithm" / "methods"


@router.get("/method-files")
async def list_method_files(_: str = Depends(get_current_user)):
    if not METHODS_ROOT.exists():
        raise HTTPException(status_code=404, detail="Methods folder not found")

    result: dict[str, list[dict[str, str]]] = {}
    for method_dir in sorted(METHODS_ROOT.iterdir()):
        if not method_dir.is_dir():
            continue
        files: list[dict[str, str]] = []
        for file_path in sorted(method_dir.glob("*.py")):
            files.append(
                {
                    "name": file_path.name,
                    "path": str(file_path.relative_to(METHODS_ROOT)).replace("\\", "/"),
                    "content": file_path.read_text(encoding="utf-8"),
                }
            )
        result[method_dir.name] = files
    return result



# --- Behaviour runs -----------------------------------------------------------
#
# Running an algorithm from the dashboard. A run opens a real browser on the
# machine hosting the backend and drives it with app.behaviour, which takes tens
# of seconds - so starting one returns immediately and the client polls.


class BehaviourRunRequest(BaseModel):
    scenario: str = "feed-lab"
    identity: str = Field(default="feed-reader-1", min_length=1, max_length=64)
    want: int = Field(default=6, ge=1, le=50)
    headless: bool = False
    # Draws the simulated pointer so a headed run can be watched. Debug only:
    # the overlay is an element in the page and any site can detect it.
    show_cursor: bool = False
    # Overrides the scenario's own URL, for pointing the same algorithm at a
    # different host or port without editing the scenario.
    url: Optional[str] = None


@router.get("/behaviour-scenarios")
async def list_behaviour_scenarios(_: str = Depends(get_current_user)):
    """The pages this algorithm knows how to read, and what it reads from each."""
    return behaviour_run_service.list_scenarios()


@router.get("/behaviour-runs")
async def list_behaviour_runs(limit: int = 10, _: str = Depends(get_current_user)):
    return behaviour_run_service.list_runs(limit)


@router.get("/behaviour-runs/{run_id}")
async def get_behaviour_run(run_id: str, _: str = Depends(get_current_user)):
    run = behaviour_run_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No such run")
    return run


@router.post("/behaviour-runs", status_code=202)
async def start_behaviour_run(
    body: BehaviourRunRequest,
    _: str = Depends(get_current_user),
):
    """Starts a run and returns its id straight away. 202 rather than 201: the
    work has been accepted, not finished - poll the run for the result."""
    if body.scenario not in behaviour_run_service.SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario (known: {', '.join(behaviour_run_service.SCENARIOS)})",
        )
    run = behaviour_run_service.start_run(
        body.scenario,
        identity=body.identity,
        want=body.want,
        headless=body.headless,
        show_cursor=body.show_cursor,
        url=body.url,
    )
    return run.as_dict()
