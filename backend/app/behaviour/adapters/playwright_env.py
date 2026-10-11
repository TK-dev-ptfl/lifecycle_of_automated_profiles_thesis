"""Environment over a real Playwright page.

Deliberately thin. Everything interesting - how a cursor travels, how long a
person hesitates, when to overshoot - lives in the behaviour layer and is already
tested against the simulator. This file's only job is to answer the four
questions the Environment port asks, in Playwright's terms.

Target.query is read as a CSS selector here. That is this adapter's choice, not
the port's: another adapter is free to read the same string as a role, an
accessibility label, or a name in its own world.
"""
from __future__ import annotations

import asyncio
import time
from typing import Mapping, Optional

from playwright.async_api import Page

from app.behaviour.environment import Box, CollectedItem, Observation, Target

DEFAULT_VIEWPORT = {"width": 1366, "height": 900}


class PlaywrightEnvironment:
    """Wraps a Page so the behaviour layer can drive it without importing
    Playwright anywhere above this module."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.mouse = page.mouse
        self.keyboard = page.keyboard
        self._started = time.monotonic()

    def viewport(self) -> Box:
        size = self.page.viewport_size or DEFAULT_VIEWPORT
        return Box(0, 0, size["width"], size["height"])

    async def observe(self, target: Target) -> Observation:
        """Looks at a target without touching it.

        Never raises: a missing element is an observation ("it is not there"), not
        an error. That is what lets the executor poll for something to appear and
        decide for itself, with the profile's patience, when to give up - instead
        of each call site inventing its own timeout.
        """
        try:
            locator = self.page.locator(target.query).first
            if await locator.count() == 0:
                return Observation(exists=False)

            visible = await locator.is_visible()
            raw = await locator.bounding_box() if visible else None
            box = Box(raw["x"], raw["y"], raw["width"], raw["height"]) if raw else None

            # Only inputs have a value, and asking a div for one throws.
            value = ""
            try:
                value = await locator.input_value(timeout=250)
            except Exception:
                pass

            text = ""
            try:
                text = (await locator.inner_text(timeout=250)).strip()
            except Exception:
                pass

            return Observation(exists=True, visible=visible, box=box, value=value, text=text)
        except Exception:
            # A detached node mid-render, a navigation in flight: not there right
            # now, ask again shortly.
            return Observation(exists=False)

    async def scroll_by(self, dy: float) -> None:
        """Scrolls with a wheel event at the cursor, not window.scrollBy.

        A script-driven scroll is a scroll with no input behind it - no wheel,
        no key, no touch - which is exactly what a page checks for. A wheel
        event is trusted input; it also scrolls whatever is under the cursor,
        just as a real wheel does.
        """
        await self.mouse.wheel(0, dy)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def now(self) -> float:
        return time.monotonic() - self._started

    async def collect(self, target: Target, fields: Mapping[str, str]) -> list[CollectedItem]:
        """Every element matching `target`, with `fields` read from inside each.

        Field queries are resolved *relative to the item*, not the page, which is
        what makes them reusable: ".author" means this post's author, however many
        posts there are. A missing field is an empty string rather than an error -
        feeds are inconsistent (a post with no image, a repost with no body) and
        one absent field should not lose the whole item.
        """
        items: list[CollectedItem] = []
        try:
            matches = self.page.locator(target.query)
            count = await matches.count()
        except Exception:
            return items

        viewport = self.viewport()
        for index in range(count):
            item = matches.nth(index)
            try:
                raw = await item.bounding_box()
            except Exception:
                raw = None
            # bounding_box() answers for anything laid out, including posts
            # thousands of pixels below the fold. The port's contract is that an
            # item has a box only while it is on screen, so off-screen ones get
            # none here, as they do in the simulator.
            on_screen = bool(raw) and raw["y"] + raw["height"] > 0 and raw["y"] < viewport.height
            box = Box(raw["x"], raw["y"], raw["width"], raw["height"]) if on_screen else None

            values: dict[str, str] = {}
            if box is None:
                # Nothing can read an off-screen post, so its fields are not
                # fetched: on a long feed that is most of the round trips.
                items.append(CollectedItem(index=index, box=None, fields=values))
                continue
            for name, query in fields.items():
                try:
                    node = item.locator(query).first
                    values[name] = (
                        (await node.inner_text(timeout=400)).strip()
                        if await node.count() > 0
                        else ""
                    )
                except Exception:
                    values[name] = ""
            items.append(CollectedItem(index=index, box=box, fields=values))
        return items
