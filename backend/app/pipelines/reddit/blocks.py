"""Detecting Reddit refusing to serve this IP at all.

Separate from the steps because more than one of them needs it: the block can
appear on the first navigation, or later once Reddit has had a better look at the
session.
"""
from __future__ import annotations

from app.pipelines.reddit import selectors
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.errors import step_error


async def page_is_blocked(ctx: RedditSignupContext) -> bool:
    """Whether the current page is Reddit's network-security dead end."""
    page = ctx.require_page()
    try:
        body = await page.locator(selectors.BLOCKED_SELECTOR).first.inner_text()
    except Exception:
        return False
    return selectors.BLOCKED_TEXT.lower() in body.lower()


async def raise_if_blocked(ctx: RedditSignupContext, step_name: str) -> None:
    """Fails the run with an "ip_blocked" error when Reddit has refused this IP.

    The prefix is load-bearing: identity_service classifies it as a proxy failure
    (see IP_BLOCKED_MARKER), so the proxy is flagged as not working and the whole
    run restarts on a different one. Treating it as an ordinary step failure would
    stop the run dead on a problem that a different address simply does not have.
    """
    if await page_is_blocked(ctx):
        ctx.record("Reddit served its network-security block page - this proxy's IP is refused")
        raise step_error(
            "ip_blocked",
            f"Reddit blocked this IP at {step_name} - a different proxy is needed",
        )
