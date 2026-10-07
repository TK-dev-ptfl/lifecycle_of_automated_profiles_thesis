"""Everything a Reddit signup run carries between its steps.

Separate module so a step can import the context type without importing its
sibling steps, which is what keeps the steps genuinely independent of each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from playwright.async_api import BrowserContext, Page

from app.behaviour.algorithms.cursor import Cursor


async def _no_manual_gate(prompt: str) -> None:
    """Default for standalone runs: there is nobody to ask, so don't pretend to
    wait. identity_service replaces this with the dashboard's per-identity gate."""
    print(f"[reddit-signup] manual step with no gate wired up, continuing: {prompt}")


@dataclass
class RedditSignupContext:
    """Shared state for one signup attempt.

    `email` is the mailbox already created for this identity by the email
    pipeline - Reddit's signup form is where it finally gets used, and the run
    cannot proceed without one, so it is required rather than optional.
    """

    email: str
    context: BrowserContext
    page: Optional[Page] = None
    # Created once the first page exists, then shared by every step, so the
    # pointer's position carries across the whole session instead of each step
    # starting from a fresh unknown origin.
    cursor: Optional[Cursor] = None
    log: list[str] = field(default_factory=list)

    # Blocks until a human confirms on the Pipelines page. Used by the humanity
    # check, and by the wait for email verification.
    wait_for_manual: Callable[[str], Awaitable[None]] = _no_manual_gate
    # Forwards each record() live to the dashboard - see
    # app.pipelines.email_pool.progress.add_log.
    on_log: Optional[Callable[[str], None]] = None

    # Set by step_humanity_check so later steps (and the logs) can tell a run
    # that had to solve a challenge from one that was never shown it.
    humanity_challenge_shown: bool = False

    def record(self, message: str) -> None:
        self.log.append(message)
        print(f"[reddit-signup] {message}")
        if self.on_log:
            self.on_log(message)

    def require_page(self) -> Page:
        """Steps after the first can assume a page exists; this turns a
        programming mistake into a readable failure rather than an AttributeError
        on None halfway through a browser session."""
        if self.page is None:
            raise RuntimeError("no page open yet - step_open_homepage must run first")
        return self.page

    def require_cursor(self) -> Cursor:
        if self.cursor is None:
            raise RuntimeError("no cursor yet - step_open_homepage must run first")
        return self.cursor
