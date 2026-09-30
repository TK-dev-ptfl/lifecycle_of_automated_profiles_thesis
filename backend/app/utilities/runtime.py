"""Runtime environment checks for things that break the browser pipeline in ways
the resulting exception does not explain."""
from __future__ import annotations

import asyncio
import sys
from typing import Optional


def browser_launch_blocked_reason() -> Optional[str]:
    """Why Playwright cannot launch a browser on the *current* event loop, or
    None if it can.

    There is exactly one cause today, and it is worth a dedicated check because
    the symptom is unreadable: on Windows, asyncio's SelectorEventLoop does not
    implement subprocess support, so launching Chromium raises a bare
    `NotImplementedError` with no message and no useful traceback frame of ours.

    That loop gets selected by accident rather than by choice - uvicorn switches
    to WindowsSelectorEventLoopPolicy whenever it needs to run the server in a
    subprocess itself, i.e. with `--reload` or `--workers N` (see
    uvicorn/loops/asyncio.py). So the pipeline works when the server is started
    plainly and breaks the moment someone adds `--reload`, which is not a
    connection anybody makes from `NotImplementedError:` alone.
    """
    if sys.platform != "win32":
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    if not isinstance(loop, asyncio.SelectorEventLoop):
        return None
    return (
        "this event loop cannot start subprocesses, so Playwright cannot launch a browser "
        f"({type(loop).__name__} on Windows). uvicorn selects it when it runs the server in a "
        "subprocess - that means --reload or --workers. Start the backend without --reload "
        "(python -m uvicorn app.main:app --port 8000), or use backend/run.py, which keeps "
        "reloading and forces the Proactor loop that does support subprocesses."
    )
