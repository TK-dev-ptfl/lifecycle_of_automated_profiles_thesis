"""Step 5 - type the identity's mailbox into the dialog, and verify it landed."""
from __future__ import annotations

from app.behaviour.algorithms.forms import fill_field
from app.pipelines.reddit import selectors
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error

FIELD_TIMEOUT_MS = 15_000


async def _find_email_field(ctx: RedditSignupContext):
    page = ctx.require_page()
    for selector in selectors.EMAIL_FIELD_CANDIDATES:
        candidate = page.locator(f"{selectors.SIGNUP_DIALOG} {selector}").first
        try:
            await candidate.wait_for(state="visible", timeout=FIELD_TIMEOUT_MS)
            return candidate, selector
        except Exception:
            continue
    raise step_error(
        "enter_email",
        f"no email field in the signup dialog (tried {', '.join(selectors.EMAIL_FIELD_CANDIDATES)})",
    )


async def step_enter_email(ctx: RedditSignupContext) -> None:
    if not ctx.email:
        # Nothing to recover from: the whole point of this run is to register the
        # mailbox the email pipeline produced for this identity.
        raise step_error("enter_email", "identity has no email address to register with")

    field, used = await _find_email_field(ctx)
    ctx.record(f"Email field located via {used}")

    box = await field.bounding_box()
    if box is None:
        raise step_error("enter_email", "email field has no bounding box, cannot click into it")

    await fill_field(
        ctx.require_cursor(),
        ctx.require_page(),
        box,
        ctx.email,
        # No deliberate typos here. Reddit validates this field as you type, and a
        # transient malformed address can latch an error state that then has to be
        # cleared - a realism flourish that costs reliability is not worth it.
        typo_chance=0.0,
        log=ctx.record,
    )

    # Verified rather than assumed: per-key typing can be swallowed by a field
    # that re-rendered mid-stream, and finding that out here beats submitting a
    # half-typed address.
    actual = await field.input_value()
    if actual.strip() != ctx.email:
        raise step_error(
            "enter_email",
            f"email field contains {actual!r}, expected {ctx.email!r} - typing did not register",
        )
    ctx.record(f"Email field verified as {ctx.email}")
