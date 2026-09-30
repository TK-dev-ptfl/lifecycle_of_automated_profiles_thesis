"""Dev entrypoint that keeps auto-reload AND a browser-capable event loop.

    python run.py

Why this exists: on Windows, `uvicorn --reload` switches asyncio to
WindowsSelectorEventLoopPolicy (uvicorn/loops/asyncio.py does this whenever it
runs the server in a subprocess). A SelectorEventLoop cannot start subprocesses,
so Playwright cannot launch Chromium and every signup pipeline dies with a bare,
unexplained `NotImplementedError`.

Setting the Proactor policy here and passing loop="none" tells uvicorn to leave
the policy alone, so reloading and browser launching both work. The policy is set
at import time on purpose: the reloader re-imports this module in each worker
process, so the child that actually serves requests gets it too.
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn  # noqa: E402  - must come after the policy is set

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # Without this, uvicorn re-applies its own policy and undoes the above.
        loop="none",
    )
