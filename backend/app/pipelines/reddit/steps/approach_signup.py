"""Step 3 - wander the cursor about, then go and click Sign up.

The wandering is not decoration. Arriving on a page and immediately moving in one
straight line to the single button you intend to press is a strong automation
signal; a person's pointer drifts around while they read. Both halves of this step
come from app.behaviour, which is where all the decisions about how a hand
actually moves live.
"""
from __future__ import annotations

import random

from app.behaviour.algorithms.cursor import approach_and_click, idle_drags
from app.pipelines.reddit import selectors
from app.pipelines.reddit.blocks import raise_if_blocked
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error

BUTTON_TIMEOUT_MS = 20_000
# A couple of gestures is enough to break the straight-line pattern; a dozen would
# just be a different, equally mechanical signature.
IDLE_DRAG_RANGE = (2, 4)


async def _find_signup_button(ctx: RedditSignupContext):
    """The header link, by id, falling back to any link to the register route."""
    page = ctx.require_page()
    for selector in (selectors.SIGNUP_BUTTON, selectors.SIGNUP_LINK_FALLBACK):
        candidate = page.locator(selector).first
        try:
            await candidate.wait_for(state="visible", timeout=BUTTON_TIMEOUT_MS)
            return candidate, selector
        except Exception:
            continue
    # Reddit can decide mid-session that it does not like this address, and the
    # symptom is simply that the page no longer has a signup button on it. Check
    # before blaming the selectors - one is a proxy to swap, the other is markup
    # to fix, and they want completely different responses.
    await raise_if_blocked(ctx, "approach_signup")
    raise step_error(
        "approach_signup",
        f"no signup button found (tried {selectors.SIGNUP_BUTTON} and {selectors.SIGNUP_LINK_FALLBACK})",
    )


async def step_approach_signup(ctx: RedditSignupContext) -> None:
    cursor = ctx.require_cursor()

    count = random.randint(*IDLE_DRAG_RANGE)
    performed = await idle_drags(cursor, count, log=ctx.record)
    ctx.record(f"Performed {performed} idle mouse drag(s) before approaching the signup button")

    button, used = await _find_signup_button(ctx)
    ctx.record(f"Signup button located via {used}")

    box = await button.bounding_box()
    if box is None:
        # Visible but with no box means it is there in the accessibility tree and
        # not actually laid out - clicking by coordinate would hit whatever is
        # underneath it.
        raise step_error("approach_signup", "signup button has no bounding box, cannot aim at it")

    await approach_and_click(cursor, box, log=ctx.record)
    ctx.record("Clicked the signup button")
