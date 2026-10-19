"""A deliberately robotic feed reader: the negative control for the checks.

The human Actor is only evidence of anything if the same checks that pass it
fail something that is plainly a bot. This is that something. It reads the same
feed with the same schema, in the same browser with the same fingerprint and
proxy, and does everything the way a naive automation script does - so when the
scores drop, behaviour is the only thing that changed.

Every habit below is a known tell, and each one is aimed at a check:

  - acts the instant the page is ready, with no time spent looking
                                                   -> time before first action
  - moves in straight lines at constant speed, all in one burst
                                                   -> curved paths, speed rises
                                                      and falls, direction
                                                      jitter, top speed
  - clicks the exact centre of every button, with no hold
                                                   -> imprecise aim, natural
                                                      press length
  - scrolls by script, a fixed distance on a fixed beat
                                                   -> scrolling follows input,
                                                      pauses to read
  - reads posts that were never on screen, all for the same time
  - fires one click from JavaScript                -> events come from real input
  - types at a perfectly even rhythm with no key hold, and fills one field
    without typing at all                          -> keystroke rhythm, text
                                                      arrives through keys

It talks to the Playwright page directly rather than through the Environment
port: being browser-shaped and unportable is part of what it models, and none
of it should ever be reused for anything but this comparison.
"""
from __future__ import annotations

import asyncio
from typing import Callable

from app.behaviour.goals import FeedSchema

# One beat for everything. A constant interval between actions is the most
# recognisable rhythm there is.
BEAT_S = 1.0
SCROLL_PX = 400
MOVE_STEPS = 8


class RoboticActor:
    def __init__(self, page, log: Callable[[str], None] = lambda _m: None) -> None:
        self.page = page
        self.log = log
        self.collected: list[dict] = []

    async def _move(self, x: float, y: float) -> None:
        # Playwright's own interpolation: a straight line, evenly spaced, sent
        # in one burst with no time between samples.
        await self.page.mouse.move(x, y, steps=MOVE_STEPS)

    async def _click_centre(self, locator) -> bool:
        box = await locator.bounding_box()
        if not box:
            return False
        await self._move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await self.page.mouse.down()
        await self.page.mouse.up()
        return True

    async def click(self, query: str) -> bool:
        """Exact-centre, zero-hold click on the first match of a CSS query."""
        locator = self.page.locator(query).first
        await locator.scroll_into_view_if_needed()
        return await self._click_centre(locator)

    async def read_feed(self, schema: FeedSchema, want: int, task=None) -> list[dict]:
        """Reads `want` posts, then does the same task the human-like run does
        (behaviour_run_service.FeedTask: likes, one comment, one post), so both
        are graded on the same acts. Any object with `likes`, `comment` and
        `post` will do; without one, every post read is liked."""
        likes = task.likes if task is not None else want
        items = self.page.locator(schema.item.query)
        # Straight to work: the first input lands immediately after load.
        await self._move(40, 40)

        for index in range(want):
            if index >= await items.count():
                break
            item = items.nth(index)
            # Read without looking: the fields come out whether or not the post
            # was ever on screen.
            fields = {}
            for name, query in schema.fields.items():
                node = item.locator(query).first
                fields[name] = (await node.inner_text()).strip() if await node.count() else ""
            self.collected.append(fields)

            await self.page.evaluate(f"window.scrollBy(0, {SCROLL_PX})")
            await asyncio.sleep(BEAT_S)

            like = item.locator(".act.like").first
            if index < likes and await like.count():
                await like.scroll_into_view_if_needed()
                await self._click_centre(like)
            if index == 1:
                # The JavaScript click: an event no input device produced.
                await item.locator(".act.rep").first.evaluate("el => el.click()")
            self.log(f"read item {index} in {BEAT_S:.1f}s (robotic): {fields.get('body', '')[:40]!r}")
            await asyncio.sleep(BEAT_S)

        await self._comment(items.first, task.comment if task is not None else "Great post, thanks for sharing")
        await self._post(task.post if task is not None else "Automated post number one")
        self.log(f"read {len(self.collected)} item(s), robotically")
        return self.collected

    async def _comment(self, post, text: str) -> None:
        """Opens the comments and types at a metronome's pace, keys held for
        no time at all."""
        await post.scroll_into_view_if_needed()
        if not await self._click_centre(post.locator(".act.cmt-btn").first):
            return
        field = post.locator(".reply-in").first
        await self._click_centre(field)
        await self.page.keyboard.type(text, delay=40)
        await self.page.keyboard.press("Enter")
        self.log("commented at a constant 40 ms per key")
        await asyncio.sleep(BEAT_S)

    async def _post(self, text: str) -> None:
        """Fills the composer outright - text with no key presses behind it."""
        composer = self.page.locator("#composer")
        if not await composer.count():
            return
        await composer.scroll_into_view_if_needed()
        await composer.fill(text)
        await self.click("#postBtn")
        self.log("posted by filling the field directly")
        await asyncio.sleep(BEAT_S)
