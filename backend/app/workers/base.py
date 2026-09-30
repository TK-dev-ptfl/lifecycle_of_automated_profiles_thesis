"""Shared machinery for the long-lived background loops in this package.

Each worker is a single asyncio.Task on the FastAPI app's own event loop -
started from the lifespan handler or the /api/workers endpoints, cancelled on
shutdown. No Redis/arq involved: these loops are part of the same process that
runs the pipelines, which is what lets the scheduler simply await
start_email_pipeline_for_identity and treat "the await returned" as "the slot
is free".
"""
from __future__ import annotations

import asyncio
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# Enough history for the dashboard to show what a worker has been doing
# without letting a worker that's been up for days grow without bound.
MAX_LOG_LINES = 200


class LoopWorker:
    """Runs run_once() forever, interval_s apart, until stopped.

    The loop body deliberately cannot kill the worker: run_once's exceptions
    are recorded and logged, then the loop sleeps and tries again. A single
    failed scrape or one bad pipeline must not silently take the whole worker
    down - the whole point of these two workers is that their invariants
    ("seven pipelines are running", "the pool is fresh") keep holding
    indefinitely without anyone watching. asyncio.CancelledError is the one
    exception re-raised untouched, so stop() actually stops.
    """

    name = "worker"
    interval_s: float = 60.0

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._logs: deque[str] = deque(maxlen=MAX_LOG_LINES)
        self._started_at: Optional[datetime] = None
        self._last_run_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._cycles = 0

    # --- lifecycle -------------------------------------------------------
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> bool:
        """True if this call started the loop, False if it was already up
        (so a double POST /start is a no-op rather than a second loop racing
        the first one)."""
        if self.is_running():
            return False
        self._started_at = datetime.now(timezone.utc)
        self._last_error = None
        self._task = asyncio.create_task(self._loop(), name=f"worker:{self.name}")
        self.log("started")
        return True

    async def stop(self) -> bool:
        """True if this call stopped a running loop. Awaits the cancellation
        so anything the worker holds open (DB sessions, in-flight cleanup in a
        finally block) is actually released before this returns."""
        if not self.is_running():
            self._task = None
            return False
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.log("stopped")
        return True

    # --- introspection ---------------------------------------------------
    def status(self) -> dict:
        status = {
            "name": self.name,
            "running": self.is_running(),
            "interval_s": self.interval_s,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "cycles": self._cycles,
            "last_error": self._last_error,
            "logs": list(self._logs),
        }
        status.update(self.extra_status())
        return status

    def extra_status(self) -> dict:
        """Worker-specific fields for the status payload."""
        return {}

    def log(self, message: str) -> None:
        self._logs.append(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} {message}")
        print(f"[{self.name}] {message}")

    # --- the loop --------------------------------------------------------
    async def _loop(self) -> None:
        while True:
            self._last_run_at = datetime.now(timezone.utc)
            try:
                await self.run_once()
                self._last_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self.log(f"cycle failed: {self._last_error}")
                print(traceback.format_exc())
            self._cycles += 1
            await asyncio.sleep(self.interval_s)

    async def run_once(self) -> None:
        raise NotImplementedError
