"""Cursor algorithms: getting somewhere, and looking busy on the way.

These compose the mouse primitives into the two things a pipeline actually wants
- "wander about for a moment" and "go and click that" - and are the only place
that needs to know a cursor has a current position at all.
"""
from __future__ import annotations

import random
from typing import Callable, Optional

from app.behaviour.primitives import mouse as mouse_primitives
from app.behaviour.primitives.timing import Sleeper, _real_sleep, pause, think
from app.behaviour.protocols import ViewportPageLike

Point = tuple[float, float]
Logger = Callable[[str], None]

DEFAULT_VIEWPORT = {"width": 1366, "height": 900}


class Cursor:
    """Tracks where the pointer is, which Playwright does not expose.

    Every path has to start from somewhere, and without this each move would have
    to begin by teleporting to a known origin - which is itself the artefact we
    are trying to avoid. One of these lives on a pipeline's context for the whole
    session.
    """

    def __init__(self, page: ViewportPageLike, at: Optional[Point] = None) -> None:
        self.page = page
        size = page.viewport_size or DEFAULT_VIEWPORT
        self.width = size["width"]
        self.height = size["height"]
        # Starting somewhere arbitrary rather than (0, 0): a session whose first
        # motion begins in the very corner of the window is a tell on its own.
        self.at: Point = at or (
            random.uniform(0.2, 0.8) * self.width,
            random.uniform(0.2, 0.8) * self.height,
        )

    def random_point(self, margin: float = 0.08) -> Point:
        """Somewhere inside the viewport, off the extreme edges."""
        return (
            random.uniform(margin, 1 - margin) * self.width,
            random.uniform(margin, 1 - margin) * self.height,
        )

    async def move_to(self, point: Point, *, sleeper: Sleeper = _real_sleep) -> list[Point]:
        path = await mouse_primitives.move_to(self.page.mouse, self.at, point, sleeper=sleeper)
        self.at = point
        return path

    async def drag_to(self, point: Point, *, sleeper: Sleeper = _real_sleep) -> list[Point]:
        path = await mouse_primitives.drag(self.page.mouse, self.at, point, sleeper=sleeper)
        self.at = point
        return path


async def idle_drags(
    cursor: Cursor,
    count: int = 3,
    *,
    sleeper: Sleeper = _real_sleep,
    log: Logger = lambda _m: None,
) -> int:
    """A few aimless press-move-release gestures around the page, with pauses.

    What a person does while reading and deciding: selecting a bit of text,
    dragging nothing in particular, hesitating. Each gesture starts from wherever
    the last one ended, so the whole sequence is one continuous path rather than a
    set of unrelated jumps.

    Returns the number of gestures performed.
    """
    done = 0
    for i in range(max(0, count)):
        target = cursor.random_point()
        await cursor.drag_to(target, sleeper=sleeper)
        done += 1
        log(f"idle drag {i + 1}/{count} to ({target[0]:.0f}, {target[1]:.0f})")
        # Between gestures, not within them - this is the hesitation, not travel.
        await pause(0.7, spread=0.6, cap_s=4.0, sleeper=sleeper)
    return done


async def approach_and_click(
    cursor: Cursor,
    box: dict,
    *,
    sleeper: Sleeper = _real_sleep,
    log: Logger = lambda _m: None,
) -> Point:
    """Travels to an element and clicks it the way a hand would.

    Four parts, each of which exists because its absence is detectable:
      - aim somewhere inside the box rather than its exact centre
      - on a long trip, fly slightly past and settle back (ballistic overshoot)
      - pause before pressing - the cursor arrives before the decision does
      - hold the button down for a measurable moment

    Takes a bounding_box() dict rather than a locator so it stays independent of
    how the caller found the element. Returns the point actually clicked.
    """
    target = mouse_primitives.landing_point(box)

    overshoot = mouse_primitives.overshoot_point(target, cursor.at)
    if overshoot is not None:
        await cursor.move_to(overshoot, sleeper=sleeper)
        log(f"overshot to ({overshoot[0]:.0f}, {overshoot[1]:.0f}), correcting")

    await cursor.move_to(target, sleeper=sleeper)
    await think(sleeper=sleeper)
    await mouse_primitives.click_at(cursor.page.mouse, target, sleeper=sleeper)
    log(f"clicked ({target[0]:.0f}, {target[1]:.0f})")
    return target
