"""The Reddit signup pipeline: the step order, and the runner that executes it.

This module is the only place that knows what order the steps go in. Each step is
a module in steps/ that imports the context and the behaviour layer and nothing
else, so reordering, replacing or skipping one is an edit here rather than a
refactor.

Stops after the email verification wait - that is as far as the flow is specified
so far. PIPELINE_STEPS is where the rest gets appended.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from playwright.async_api import async_playwright

from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.steps.approach_signup import step_approach_signup
from app.pipelines.reddit.steps.await_email_verification import step_await_email_verification
from app.pipelines.reddit.steps.enter_email import step_enter_email
from app.pipelines.reddit.steps.humanity_check import step_humanity_check
from app.pipelines.reddit.steps.open_homepage import step_open_homepage
from app.pipelines.reddit.steps.signup_dialog import step_await_signup_dialog
from app.pipelines.reddit.steps.submit_email import step_submit_email


@dataclass(frozen=True)
class RedditStep:
    """One named step.

    manual=True marks a step that can block for a human on the Pipelines page.
    The humanity check is manual *conditionally* - it waits only when Reddit
    actually shows the challenge - but it is declared manual because the dashboard
    needs to know a Continue button might be required, and a step that sometimes
    needs one has to be treated as one that does.
    """

    name: str
    fn: Callable[[RedditSignupContext], Awaitable[None]]
    manual: bool = False


PIPELINE_STEPS: list[RedditStep] = [
    RedditStep("open_homepage", step_open_homepage),
    RedditStep("humanity_check", step_humanity_check, manual=True),
    RedditStep("approach_signup", step_approach_signup),
    RedditStep("await_signup_dialog", step_await_signup_dialog),
    RedditStep("enter_email", step_enter_email),
    RedditStep("submit_email", step_submit_email),
    RedditStep("await_email_verification", step_await_email_verification, manual=True),
]


def describe_pipeline() -> list[dict]:
    """Step names and which ones can need a human - what the dashboard renders a
    progress list from, before the run has produced anything."""
    return [{"name": step.name, "manual": step.manual} for step in PIPELINE_STEPS]


@dataclass
class RedditSignupResult:
    email: str
    humanity_challenge_shown: bool
    log: list[str]


async def run_reddit_signup_pipeline(
    *,
    email: str,
    proxy: Optional[dict] = None,
    on_step: Optional[Callable[[int, RedditStep], None]] = None,
    wait_for_manual: Optional[Callable[[str], Awaitable[None]]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    headless: bool = False,
) -> RedditSignupResult:
    """Runs every step in order against one browser session.

    proxy is a Playwright proxy config and is applied at launch, which binds it to
    the whole browser - every context, page and request for the session. Same as
    the email pipeline; see identity_service._proxy_to_playwright_config.

    headless defaults to False because the humanity challenge needs a person to
    see and solve it. A headless run can still complete when Reddit doesn't show
    the challenge, but there is no way to know that in advance.

    Certificate validation is deliberately left on (no ignore_https_errors): a
    proxy that intercepts TLS can read and rewrite everything in the session,
    including the credentials being typed into it.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, proxy=proxy)
        try:
            context = await browser.new_context(viewport={"width": 1366, "height": 900})
            # Unbounded per-action waits: each step asserts its own outcome with
            # its own timeout, and the outer stall guard in identity_service is
            # what kills a run that stops making progress. A global default here
            # would fail slow-but-fine steps.
            context.set_default_timeout(0)

            ctx = RedditSignupContext(email=email, context=context, on_log=on_log)
            if wait_for_manual is not None:
                ctx.wait_for_manual = wait_for_manual

            for index, step in enumerate(PIPELINE_STEPS):
                if on_step is not None:
                    on_step(index, step)
                ctx.record(f"--- step {index + 1}/{len(PIPELINE_STEPS)}: {step.name} ---")
                await step.fn(ctx)

            return RedditSignupResult(
                email=ctx.email,
                humanity_challenge_shown=ctx.humanity_challenge_shown,
                log=list(ctx.log),
            )
        finally:
            # Runs on cancellation too, which is how the stall guard and the
            # scheduler's stop() avoid leaving Chromium instances behind.
            await browser.close()
