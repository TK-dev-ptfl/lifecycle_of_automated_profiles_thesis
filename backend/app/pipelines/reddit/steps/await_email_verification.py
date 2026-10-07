"""Step 7 - wait for Reddit's verification email to be dealt with.

This is where the signup run hands off to the mailbox. Reddit has sent a mail to
the Tuta address; something has to open it and act on the code or link before the
browser can carry on.

Right now that something is a person, confirming on the Pipelines page - the same
gate the humanity check uses. Reading the mailbox automatically is not built yet
(app/pipelines/email_pool/providers/ has a signup pipeline for Tuta but nothing
that reads mail), so this step is the seam where it will plug in: replace the
gate wait with a poll of the provider's fetch_verification and the rest of the
pipeline does not change.

Deliberately manual rather than a fixed sleep. A sleep that is too short
continues before the mail arrives and a sleep that is long enough to be safe
wastes minutes of every run - and neither one can tell whether the mail arrived
at all.
"""
from __future__ import annotations

from app.pipelines.reddit.context import RedditSignupContext


async def step_await_email_verification(ctx: RedditSignupContext) -> None:
    ctx.record(
        f"Reddit should have sent a verification mail to {ctx.email} - waiting for it to be "
        "handled, then confirm on the Pipelines page"
    )

    await ctx.wait_for_manual(
        f"Open {ctx.email}, complete Reddit's email verification, then confirm here."
    )

    ctx.record("Email verification confirmed")
