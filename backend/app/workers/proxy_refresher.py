"""Keeps the proxy list on the Proxies page fresh.

Every REFRESH_INTERVAL_S it re-scrapes both configured free sources and swaps
the free part of the pool for the result (see
proxy_service.replace_free_proxy_pool for exactly what "free part" means and
why the swap happens in that order). This is the only thing in the system that
scrapes on a schedule - the pipeline scheduler deliberately never scrapes, it
just consumes whatever this worker has put in the table.
"""
from __future__ import annotations

from typing import Optional

from app.database import AsyncSessionLocal
from app.services import proxy_service
from app.workers.base import LoopWorker

# Two minutes, as specified: free proxies rotate on the order of minutes, so
# a list older than that is mostly dead weight the scheduler would waste
# health checks on.
REFRESH_INTERVAL_S = 120.0


class ProxyRefresher(LoopWorker):
    name = "proxy-refresher"
    interval_s = REFRESH_INTERVAL_S

    def __init__(self) -> None:
        super().__init__()
        self._last_result: Optional[dict] = None

    async def run_once(self) -> None:
        # Own session, not a request-scoped one - this loop outlives every
        # request and must not hold a session open between cycles.
        async with AsyncSessionLocal() as db:
            result = await proxy_service.replace_free_proxy_pool(db)
        self._last_result = result

        if result.get("error"):
            # Both sources failed, so the old list was left in place on
            # purpose - say so rather than reporting a successful no-op.
            self.log(f"refresh failed, kept the existing list: {result['error']}")
            return

        self.log(
            f"pool replaced: {result['removed']} stale free entr"
            f"{'y' if result['removed'] == 1 else 'ies'} dropped, "
            f"{result['imported']} imported, "
            f"{result['skipped']} skipped (already known or already used)"
        )

    def extra_status(self) -> dict:
        return {"last_result": self._last_result}


# One instance per process - started from main.py's lifespan and reachable
# from the /api/workers routes.
proxy_refresher = ProxyRefresher()
