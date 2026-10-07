"""Tests for the algorithms - the compositions pipelines actually call.

These assert the shape of the combined behaviour rather than re-testing the
primitives: that idle drags form one continuous path, that an approach ends in a
real click inside the target, that filling a field focuses it before typing.
"""
from __future__ import annotations

import pytest

from app.behaviour.algorithms import cursor as cursor_algorithms
from app.behaviour.algorithms.cursor import Cursor
from app.behaviour.algorithms.forms import fill_field
from tests.behaviour.recorders import RecordingPage, RecordingSleeper

BOX = {"x": 400.0, "y": 300.0, "width": 160.0, "height": 44.0}


def _cursor(page: RecordingPage, at=(100.0, 100.0)) -> Cursor:
    return Cursor(page, at=at)


# --- Cursor ------------------------------------------------------------------

def test_cursor_does_not_start_in_the_corner():
    """A session whose first motion begins at (0, 0) is a tell on its own."""
    page = RecordingPage()
    for _ in range(50):
        c = Cursor(page)
        assert 0 < c.at[0] < page.viewport_size["width"]
        assert 0 < c.at[1] < page.viewport_size["height"]


def test_cursor_reads_the_viewport_and_falls_back_when_there_is_none():
    class NoViewport(RecordingPage):
        @property
        def viewport_size(self):
            return None

    c = Cursor(NoViewport())
    assert c.width == cursor_algorithms.DEFAULT_VIEWPORT["width"]


@pytest.mark.asyncio
async def test_cursor_tracks_its_position_across_moves():
    """Playwright does not expose pointer position, so without this every move
    would have to start by teleporting to a known origin."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page)
    await c.move_to((700.0, 500.0), sleeper=sleeper)
    assert c.at == (700.0, 500.0)
    await c.move_to((200.0, 150.0), sleeper=sleeper)
    assert c.at == (200.0, 150.0)


# --- idle_drags --------------------------------------------------------------

@pytest.mark.asyncio
async def test_idle_drags_form_one_continuous_path():
    """Each gesture must start where the last ended. Unrelated jumps between
    gestures would be exactly the discontinuity a real hand cannot produce."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page)
    logged: list[str] = []

    done = await cursor_algorithms.idle_drags(c, 3, sleeper=sleeper, log=logged.append)
    assert done == 3

    kinds = page.mouse.kinds
    assert kinds.count("down") == 3 and kinds.count("up") == 3
    # Press and release strictly alternate - no gesture starts before the last
    # one finished.
    presses = [k for k in kinds if k in ("down", "up")]
    assert presses == ["down", "up"] * 3
    assert len(logged) == 3


@pytest.mark.asyncio
async def test_idle_drags_stay_inside_the_viewport():
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page)
    await cursor_algorithms.idle_drags(c, 6, sleeper=sleeper)

    for x, y in page.mouse.path:
        # Bézier control points bow outward, so allow a small margin - what
        # matters is that gestures are not aimed off-screen.
        assert -80 <= x <= page.viewport_size["width"] + 80
        assert -80 <= y <= page.viewport_size["height"] + 80


@pytest.mark.asyncio
async def test_zero_idle_drags_does_nothing():
    page, sleeper = RecordingPage(), RecordingSleeper()
    assert await cursor_algorithms.idle_drags(_cursor(page), 0, sleeper=sleeper) == 0
    assert page.mouse.events == []


# --- approach_and_click ------------------------------------------------------

@pytest.mark.asyncio
async def test_approach_lands_inside_the_target_and_clicks_it():
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page, at=(50.0, 50.0))

    point = await cursor_algorithms.approach_and_click(c, BOX, sleeper=sleeper)

    assert BOX["x"] <= point[0] <= BOX["x"] + BOX["width"]
    assert BOX["y"] <= point[1] <= BOX["y"] + BOX["height"]
    assert page.mouse.kinds[-2:] == ["down", "up"], "approach must end in a click"
    # The press happens where the travel ended, not somewhere else.
    assert page.mouse.path[-1] == point


@pytest.mark.asyncio
async def test_approach_from_far_away_overshoots_and_comes_back():
    """Ballistic motion: the cursor passes the target then corrects."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page, at=(20.0, 320.0))

    point = await cursor_algorithms.approach_and_click(c, BOX, sleeper=sleeper)
    xs = [x for x, _ in page.mouse.path]
    assert max(xs) > point[0], "never travelled past the target"


@pytest.mark.asyncio
async def test_approach_pauses_before_pressing():
    """The cursor arrives before the decision to click does."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    await cursor_algorithms.approach_and_click(_cursor(page), BOX, sleeper=sleeper)
    # The think() pause dwarfs the few-millisecond gaps between path samples.
    assert max(sleeper.waits) > 0.1


# --- fill_field --------------------------------------------------------------

@pytest.mark.asyncio
async def test_fill_field_focuses_the_field_before_typing():
    """Typing into a field that was never clicked skips the focus event a real
    interaction always produces."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    c = _cursor(page)

    sent = await fill_field(c, page, BOX, "someone@tuta.com", sleeper=sleeper)

    assert "down" in page.mouse.kinds and "up" in page.mouse.kinds
    assert page.keyboard.pressed == list("someone@tuta.com")
    assert sent == page.keyboard.pressed


@pytest.mark.asyncio
async def test_fill_field_pauses_between_focusing_and_typing():
    """Filling a field the instant it gains focus is something no hand does, and
    inline validators often key off that gap."""
    page, sleeper = RecordingPage(), RecordingSleeper()
    await fill_field(_cursor(page), page, BOX, "abc", sleeper=sleeper)
    assert max(sleeper.waits) > 0.1


@pytest.mark.asyncio
async def test_fill_field_reports_corrections_it_made():
    page, sleeper = RecordingPage(), RecordingSleeper()
    logged: list[str] = []
    await fill_field(
        _cursor(page), page, BOX, "reddit", typo_chance=1.0, sleeper=sleeper, log=logged.append
    )
    assert any("corrected" in line for line in logged)
