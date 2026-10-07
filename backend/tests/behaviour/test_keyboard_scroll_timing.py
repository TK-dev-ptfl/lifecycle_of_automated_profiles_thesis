"""Atomic tests for the typing, scrolling and timing primitives."""
from __future__ import annotations

import statistics

import pytest

from app.behaviour.primitives import keyboard, scroll, timing
from tests.behaviour.recorders import RecordingKeyboard, RecordingPage, RecordingSleeper


# --- typing ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typing_sends_one_key_per_character():
    """Per-key presses, not Playwright's fill() - which sets the value outright
    and fires no keystroke events at all, so anything listening sees a paste."""
    kb, sleeper = RecordingKeyboard(), RecordingSleeper()
    sent = await keyboard.type_text(kb, "hello@tuta.com", sleeper=sleeper)

    assert kb.pressed == list("hello@tuta.com")
    assert sent == kb.pressed
    assert kb.typed == [], "must not fall back to bulk type()"


@pytest.mark.asyncio
async def test_keystroke_gaps_are_uneven():
    """Evenly spaced keystrokes are one of the most obvious automation tells."""
    kb, sleeper = RecordingKeyboard(), RecordingSleeper()
    await keyboard.type_text(kb, "a" * 60, sleeper=sleeper)

    assert len(sleeper.waits) == 60
    assert statistics.stdev(sleeper.waits) > 0.005, "gaps are nearly constant"


@pytest.mark.asyncio
async def test_a_typo_is_a_neighbouring_key_and_gets_corrected():
    """A plausible typo is an adjacent key followed by a backspace. A random
    letter is not a typo, it is a bug, and an uncorrected one changes the value."""
    kb, sleeper = RecordingKeyboard(), RecordingSleeper()
    sent = await keyboard.type_text(kb, "gmail", typo_chance=1.0, sleeper=sleeper)

    assert "Backspace" in sent
    # Every correction has to leave the intended text behind.
    result = []
    for key in sent:
        if key == "Backspace":
            result.pop()
        else:
            result.append(key)
    assert "".join(result) == "gmail"

    # And each wrong key must neighbour the one it stood in for.
    for i, key in enumerate(sent):
        if key == "Backspace":
            wrong = sent[i - 1]
            intended = sent[i + 1]
            assert wrong in keyboard._NEIGHBOURS[intended.lower()], (
                f"{wrong!r} is not adjacent to {intended!r}"
            )


@pytest.mark.asyncio
async def test_typing_makes_no_mistakes_by_default():
    """Fields with inline validation (an email) can latch an error state on a
    transient wrong value, so typos are opt-in."""
    kb, sleeper = RecordingKeyboard(), RecordingSleeper()
    for _ in range(20):
        kb = RecordingKeyboard()
        await keyboard.type_text(kb, "someone@example.com", sleeper=sleeper)
        assert "Backspace" not in kb.pressed


# --- scrolling ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_scroll_dispatches_one_event_per_notch():
    """A single large scrollBy has no intermediate positions - anything sampling
    scroll position sees one teleport."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    deltas = await scroll.wheel(page, 5, sleeper=sleeper)

    assert len(deltas) == 5
    assert len(page.evaluated) == 5
    assert all(d > 0 for d in deltas)


@pytest.mark.asyncio
async def test_scrolling_up_uses_negative_deltas():
    page, sleeper = RecordingPage(), RecordingSleeper()
    deltas = await scroll.wheel(page, -3, sleeper=sleeper)
    assert len(deltas) == 3 and all(d < 0 for d in deltas)


@pytest.mark.asyncio
async def test_notch_sizes_vary():
    """Wheels and trackpads do not report a constant delta."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    deltas = await scroll.wheel(page, 30, sleeper=sleeper)
    assert len(set(deltas)) > 1


@pytest.mark.asyncio
async def test_a_long_scroll_pauses_to_read_and_can_correct_back():
    page, sleeper = RecordingPage(), RecordingSleeper()
    deltas = await scroll.scroll_and_settle(page, 6, sleeper=sleeper)

    # The reading pause is the longest single wait in the sequence.
    assert max(sleeper.waits) > 0.2
    # Any correction has to be in the opposite direction to the scroll.
    assert all(d < 0 for d in deltas[6:])


# --- timing ------------------------------------------------------------------

def test_delays_are_lognormal_not_uniform():
    """Uniform noise is itself a signal - real reaction times cluster just above
    a floor with a long thin tail, they are not evenly spread across a window."""
    samples = [timing.lognormal_delay(1.0) for _ in range(4000)]
    assert statistics.median(samples) == pytest.approx(1.0, rel=0.12)
    # Right-skewed: the mean sits above the median.
    assert statistics.fmean(samples) > statistics.median(samples)
    assert max(samples) > 2.0, "no long tail at all"


def test_delays_are_never_negative_and_respect_a_cap():
    samples = [timing.lognormal_delay(2.0, cap_s=3.0) for _ in range(2000)]
    assert min(samples) >= 0.0
    assert max(samples) <= 3.0


@pytest.mark.asyncio
async def test_pause_reports_how_long_it_waited():
    sleeper = RecordingSleeper()
    waited = await timing.pause(0.5, sleeper=sleeper)
    assert sleeper.waits == [waited]


def test_typing_speed_converts_words_per_minute_to_key_gaps():
    """48 wpm at the conventional five characters per word is ~250ms per key."""
    samples = [timing.keystroke_delay_ms(48.0) for _ in range(4000)]
    assert statistics.median(samples) == pytest.approx(250.0, rel=0.15)
    # Faster typing means shorter gaps.
    fast = statistics.median([timing.keystroke_delay_ms(120.0) for _ in range(2000)])
    assert fast < statistics.median(samples)
    assert min(samples) >= 12.0, "no implausibly instant keystrokes"
