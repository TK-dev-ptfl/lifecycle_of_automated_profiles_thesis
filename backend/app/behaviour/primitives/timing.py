"""Pauses and delays, as distributions rather than constants.

Every other primitive gets its timing from here, so "how human does this run
feel" is tunable in one place and testable without waiting in real time: each
function returns the number of seconds it will sleep for, and `sleeper` can be
swapped for a recorder.
"""
from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable

Sleeper = Callable[[float], Awaitable[None]]


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def lognormal_delay(median_s: float, spread: float = 0.45, cap_s: float | None = None) -> float:
    """A delay drawn from a log-normal distribution around median_s.

    Log-normal rather than uniform because that is the shape human reaction and
    decision times actually have: a floor nobody beats, a dense cluster just
    above it, and a long thin tail of distractions. Uniform noise is itself a
    signal - real timings are never evenly spread across a window.
    """
    value = random.lognormvariate(0.0, spread) * median_s
    if cap_s is not None:
        value = min(value, cap_s)
    return max(0.0, value)


async def pause(
    median_s: float,
    spread: float = 0.45,
    cap_s: float | None = None,
    sleeper: Sleeper = _real_sleep,
) -> float:
    """Sleeps for a lognormal_delay and returns how long it slept, so callers
    can log it and tests can assert on it without the clock being involved."""
    seconds = lognormal_delay(median_s, spread=spread, cap_s=cap_s)
    await sleeper(seconds)
    return seconds


async def think(sleeper: Sleeper = _real_sleep) -> float:
    """The gap before a deliberate action - deciding to click something, moving
    on to the next field. Around half a second."""
    return await pause(0.55, spread=0.5, cap_s=4.0, sleeper=sleeper)


async def read(sleeper: Sleeper = _real_sleep) -> float:
    """Looking at something new: a page that just loaded, a modal that just
    opened. Seconds, not milliseconds, and occasionally much longer."""
    return await pause(2.2, spread=0.55, cap_s=12.0, sleeper=sleeper)


def keystroke_delay_ms(words_per_minute: float = 48.0) -> float:
    """Milliseconds between two keystrokes for a given typing speed.

    48 wpm is unremarkable touch-typing. Five characters per word is the
    standard convention for converting wpm to keystrokes. The per-key jitter is
    wide on purpose: evenly spaced keystrokes are one of the most obvious tells
    there is, and real inter-key gaps vary by a factor of several.
    """
    per_key_ms = 60_000.0 / max(1.0, words_per_minute * 5.0)
    return max(12.0, random.lognormvariate(0.0, 0.42) * per_key_ms)


def keystroke_hold_ms(median_ms: float = 86.0) -> float:
    """How long one key stays down, from keydown to keyup.

    Calibrated on the CMU keystroke benchmark (Killourhy & Maxion, DSN 2009;
    51 typists, 224,400 key holds): median 86 ms, 5th-95th percentile
    49-145 ms, and log-normal with a sigma of about 0.34. A key released the
    instant it goes down - what Playwright's press() does without a delay -
    is held for 0-2 ms, which no keyboard produces.
    """
    return min(3.0 * median_ms, max(25.0, random.lognormvariate(0.0, 0.34) * median_ms))


def reading_time_s(text: str, words_per_minute: float = 220.0) -> float:
    """How long it plausibly takes to read a passage.

    Silent reading of ordinary prose runs around 200-250 wpm, so time spent on a
    post should scale with how much it says. That matters more than it sounds:
    dwelling for a constant interval on every item regardless of length is a
    flat, machine-shaped signal, and dwelling for *no* time at all while still
    emitting scroll events is worse.

    The floor covers the glance a short post still costs - you look at it, parse
    who wrote it, and decide to move on, and that is never instant.
    """
    words = max(1, len(text.split()))
    seconds = (words / max(60.0, words_per_minute)) * 60.0
    # Jitter, because nobody reads two posts at the same speed - and skimming is
    # as human as reading, hence the wide lower spread.
    return max(0.35, lognormal_delay(seconds, spread=0.5, cap_s=seconds * 6 + 2))
