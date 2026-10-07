"""Scrolling primitives.

A wheel scroll arrives as a burst of discrete notches, not one jump, and a person
scrolling to read overshoots and comes back. One `evaluate('scrollTo')` call is
neither of those things.
"""
from __future__ import annotations

import random

from app.behaviour.primitives.timing import Sleeper, _real_sleep, pause
from app.behaviour.protocols import ViewportPageLike

# Roughly one notch of a physical wheel in CSS pixels.
NOTCH_PX = 100


async def wheel(
    page: ViewportPageLike,
    notches: int,
    *,
    sleeper: Sleeper = _real_sleep,
) -> list[int]:
    """Scrolls `notches` steps (negative scrolls up) and returns the per-notch
    deltas actually dispatched.

    Each notch is its own event with its own gap, because that is how a wheel
    reports: a single large scrollBy has no intermediate positions, so anything
    sampling scroll position sees one teleport.
    """
    direction = 1 if notches >= 0 else -1
    deltas: list[int] = []
    for _ in range(abs(notches)):
        # Notch size varies a little - trackpads and wheels are not uniform.
        delta = direction * int(NOTCH_PX * random.uniform(0.8, 1.25))
        await page.evaluate("(d) => window.scrollBy(0, d)", delta)
        deltas.append(delta)
        await sleeper(random.uniform(0.02, 0.09))
    return deltas


async def scroll_and_settle(
    page: ViewportPageLike,
    notches: int,
    *,
    sleeper: Sleeper = _real_sleep,
) -> list[int]:
    """Scrolls, pauses as if reading, then nudges back a notch or two.

    The correction is the human part: you scroll slightly too far, then come back
    to where the text you wanted actually is.
    """
    deltas = await wheel(page, notches, sleeper=sleeper)
    await pause(0.8, spread=0.5, cap_s=4.0, sleeper=sleeper)
    if abs(notches) >= 3 and random.random() < 0.6:
        back = -1 if notches > 0 else 1
        deltas += await wheel(page, back * random.randint(1, 2), sleeper=sleeper)
    return deltas
