"""Step 4 - wait for the signup dialog to actually be open.

Its own step rather than the tail of the click, because "the click landed" and
"the dialog opened" are different claims and only the second one means the run can
continue. Clicking a button proves Playwright could click something.
"""
from __future__ import annotations

from app.behaviour.primitives.timing import read
from app.pipelines.reddit import selectors
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error

DIALOG_TIMEOUT_MS = 25_000


async def step_await_signup_dialog(ctx: RedditSignupContext) -> None:
    page = ctx.require_page()
    dialog = page.locator(selectors.SIGNUP_DIALOG).first
    try:
        await dialog.wait_for(state="visible", timeout=DIALOG_TIMEOUT_MS)
    except Exception as exc:
        raise step_error(
            "await_signup_dialog",
            f"signup dialog ({selectors.SIGNUP_DIALOG}) never appeared after clicking Sign up",
        ) from exc

    label = await dialog.get_attribute("aria-label")
    ctx.record(f"Signup dialog open (aria-label={label!r})")

    # A beat to read it, as with any newly appeared surface.
    await read()
