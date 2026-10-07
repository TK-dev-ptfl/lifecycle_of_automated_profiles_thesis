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
from typing import Optional

from playwright.async_api import Page

from app.behaviour.environment import Box, Observation, Target

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
        await self.page.evaluate("(d) => window.scrollBy(0, d)", dy)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def now(self) -> float:
        return time.monotonic() - self._started
