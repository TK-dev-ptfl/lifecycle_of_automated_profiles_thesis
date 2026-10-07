"""Step 6 - click Continue, and check Reddit accepted the address."""
from __future__ import annotations

from app.behaviour.algorithms.cursor import approach_and_click
from app.behaviour.primitives.timing import pause
from app.pipelines.reddit import selectors
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error

BUTTON_TIMEOUT_MS = 15_000
# Reddit's inline validation answers in well under a second; this is only how long
# to give it before deciding no complaint is coming.
VALIDATION_SETTLE_MS = 2500


async def _find_continue_button(ctx: RedditSignupContext):
    page = ctx.require_page()
    for selector in selectors.CONTINUE_BUTTON_CANDIDATES:
        candidate = page.locator(selector).first
        try:
            await candidate.wait_for(state="visible", timeout=BUTTON_TIMEOUT_MS)
            return candidate, selector
        except Exception:
            continue
    raise step_error(
        "submit_email",
        f"no continue button in the signup dialog (tried {len(selectors.CONTINUE_BUTTON_CANDIDATES)} selectors)",
    )


async def _rejection_text(ctx: RedditSignupContext) -> str | None:
    """Reddit's complaint about the address, if it made one.

    Distinguishes "this address is taken / malformed" from "the form is still
    thinking", which otherwise look identical from out here - both are just a
    dialog that hasn't changed.
    """
    page = ctx.require_page()
    for selector in selectors.EMAIL_ERROR_CANDIDATES:
        locator = page.locator(selector).first
        try:
            if await locator.count() == 0 or not await locator.is_visible():
                continue
            text = (await locator.inner_text()).strip()
            if text:
                return text
        except Exception:
            continue
    return None


async def step_submit_email(ctx: RedditSignupContext) -> None:
    button, used = await _find_continue_button(ctx)
    ctx.record(f"Continue button located via {used}")

    box = await button.bounding_box()
    if box is None:
        raise step_error("submit_email", "continue button has no bounding box, cannot aim at it")

    await approach_and_click(ctx.require_cursor(), box, log=ctx.record)
    ctx.record("Clicked Continue")

    await pause(VALIDATION_SETTLE_MS / 1000.0, spread=0.3)

    rejection = await _rejection_text(ctx)
    if rejection:
        # Worth failing on rather than pressing through: an address Reddit won't
        # take will never produce a verification email, so every later step would
        # wait for something that is not coming.
        raise step_error("submit_email", f"Reddit rejected the email address: {rejection}")

    ctx.record("Email accepted, no inline error shown")
