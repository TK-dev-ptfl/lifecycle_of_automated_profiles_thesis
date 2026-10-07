"""Step 2 - Reddit's "Prove your humanity" interstitial, if it appears.

Conditional by design: Reddit shows this on some IPs and not others, so the step
has to be a no-op when it is absent rather than a failure. When it IS present the
run stops and waits for a person to solve it and confirm on the Pipelines page -
there is nothing to automate here, and pretending otherwise would just produce a
run that clicks Continue on an unsolved challenge.
"""
from __future__ import annotations

from app.pipelines.reddit import selectors
from app.pipelines.reddit.context import RedditSignupContext

# How long to look for the heading before concluding it was never going to appear.
# Short on purpose: this runs straight after the homepage has already reached
# domcontentloaded, so the interstitial is either in that document or it is not.
# A long wait here would add it to every single clean run.
DETECT_TIMEOUT_MS = 4000


async def _challenge_visible(ctx: RedditSignupContext) -> bool:
    page = ctx.require_page()
    heading = page.locator(selectors.HUMANITY_HEADING_SELECTOR, has_text=selectors.HUMANITY_HEADING)
    try:
        await heading.first.wait_for(state="visible", timeout=DETECT_TIMEOUT_MS)
        return True
    except Exception:
        # Not an error - the overwhelmingly common case is that it never shows.
        return False


async def step_humanity_check(ctx: RedditSignupContext) -> None:
    if not await _challenge_visible(ctx):
        ctx.record("No humanity challenge shown, skipping")
        return

    ctx.humanity_challenge_shown = True
    ctx.record(
        f'"{selectors.HUMANITY_HEADING}" challenge is on screen - waiting for a human to solve it '
        "and press Continue on the Pipelines page"
    )

    await ctx.wait_for_manual(
        f'Reddit is showing "{selectors.HUMANITY_HEADING}". Solve it in the open browser window, '
        "then confirm here."
    )

    # Confirmed by a person, so the challenge is expected to be gone. Verified
    # rather than assumed: someone can press Continue early, and finding out now
    # gives a readable failure instead of a confusing one three steps later when
    # the signup button turns out not to exist.
    if await _challenge_visible(ctx):
        ctx.record(
            f'WARNING: "{selectors.HUMANITY_HEADING}" is still on screen after confirmation - '
            "continuing anyway, but the next step will probably fail"
        )
    else:
        ctx.record("Humanity challenge cleared")
