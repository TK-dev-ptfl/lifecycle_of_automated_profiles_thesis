"""Form-filling algorithms: getting a value into a field like a person would.

Clicking a field and typing into it are separate physical acts with a gap between
them, and the gap is where most of the realism lives.
"""
from __future__ import annotations

from typing import Callable

from app.behaviour.algorithms.cursor import Cursor
from app.behaviour.primitives import keyboard as keyboard_primitives
from app.behaviour.primitives.timing import Sleeper, _real_sleep, pause, think
from app.behaviour.protocols import ViewportPageLike

Logger = Callable[[str], None]


async def fill_field(
    cursor: Cursor,
    page: ViewportPageLike,
    box: dict,
    text: str,
    *,
    words_per_minute: float = 48.0,
    typo_chance: float = 0.0,
    sleeper: Sleeper = _real_sleep,
    log: Logger = lambda _m: None,
) -> list[str]:
    """Clicks into a field, pauses, then types - returning the key sequence sent.

    The pause after focusing matters: filling a field the instant it gains focus
    is something no hand does, and inline validators often key off the gap. Typing
    goes through the keyboard primitive rather than Playwright's `fill`, which
    sets the value outright and fires no per-key events at all.

    typo_chance defaults to off. In a field validated as you type - an email, a
    username - a transient wrong value can trip a real error state that then has
    to be cleared, so making a mistake is the caller's decision, not this
    function's.
    """
    from app.behaviour.algorithms.cursor import approach_and_click

    await approach_and_click(cursor, box, sleeper=sleeper, log=log)
    await think(sleeper=sleeper)

    sent = await keyboard_primitives.type_text(
        page.keyboard,
        text,
        words_per_minute=words_per_minute,
        typo_chance=typo_chance,
        sleeper=sleeper,
    )
    corrections = sent.count("Backspace")
    log(
        f"typed {len(text)} characters"
        + (f", corrected {corrections} typo(s)" if corrections else "")
    )

    # Looking at what was typed before moving on.
    await pause(0.4, spread=0.5, cap_s=2.5, sleeper=sleeper)
    return sent
