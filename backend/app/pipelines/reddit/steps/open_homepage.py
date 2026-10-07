"""Step 1 - open reddit.com."""
from __future__ import annotations

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.behaviour.algorithms.cursor import Cursor
from app.behaviour.primitives.timing import read
from app.pipelines.reddit import selectors
from app.pipelines.reddit.blocks import raise_if_blocked
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error

# Unbounded, like the email pipeline's first navigation: this is the coldest hop
# through a freshly opened proxy connection (DNS, TCP and TLS all happening for
# the first time), and a slow proxy is not a failed one. The outer per-step stall
# guard in identity_service is what stops a genuinely wedged run.
GOTO_TIMEOUT_MS = 0
# How long to let Reddit's challenge-and-redirect dance finish before giving up
# on the homepage appearing. Generous: it is a redirect chain through whatever
# proxy this run landed on, not a page render.
SETTLE_TIMEOUT_MS = 45_000
SETTLE_POLL_MS = 500


async def step_open_homepage(ctx: RedditSignupContext) -> None:
    page = await ctx.context.new_page()
    try:
        await page.goto(selectors.HOME_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise step_error("open_homepage", f"could not load {selectors.HOME_URL}") from exc

    ctx.page = page
    # One cursor for the whole session, created here because this is where the
    # viewport first exists. Every later step moves this same pointer, so paths
    # join up instead of teleporting.
    ctx.cursor = Cursor(page)
    ctx.record(f"Opened {selectors.HOME_URL}")

    # domcontentloaded is NOT "the homepage is here". Reddit serves a
    # self-solving JS challenge first, which redirects once it passes - proceeding
    # on the first paint meant looking for a signup button on the challenge page
    # and concluding Reddit had changed its markup. Wait for an outcome that
    # actually settles the question instead.
    await _settle(ctx)

    # A moment looking at what loaded, before anything is clicked.
    await read()


async def _settle(ctx: RedditSignupContext) -> None:
    """Waits until the page is something a later step can act on.

    Three outcomes end the wait, and all three are legitimate:
      - the signup button exists  -> the homepage really arrived
      - the humanity heading      -> the next step will hand over to a human
      - the block page            -> this proxy's IP is refused, fail as such
    """
    page = ctx.require_page()
    deadline = SETTLE_TIMEOUT_MS
    waited = 0
    while waited < deadline:
        await raise_if_blocked(ctx, "open_homepage")

        for selector in (selectors.SIGNUP_BUTTON, selectors.SIGNUP_LINK_FALLBACK):
            if await page.locator(selector).count() > 0:
                ctx.record(f"Homepage settled ({selector} present)")
                return

        heading = page.locator(
            selectors.HUMANITY_HEADING_SELECTOR, has_text=selectors.HUMANITY_HEADING
        )
        if await heading.count() > 0:
            ctx.record("Homepage settled on the humanity challenge")
            return

        if selectors.JS_CHALLENGE_MARKER in page.url:
            ctx.record("Reddit's JS challenge is running, waiting for it to redirect")

        await page.wait_for_timeout(SETTLE_POLL_MS)
        waited += SETTLE_POLL_MS

    # Nothing recognisable within the budget. Checked once more so a block that
    # only rendered at the very end is still reported as a proxy problem.
    await raise_if_blocked(ctx, "open_homepage")
    raise step_error(
        "open_homepage",
        f"reddit.com did not settle into a usable page within {SETTLE_TIMEOUT_MS // 1000}s "
        f"(url={page.url})",
    )
