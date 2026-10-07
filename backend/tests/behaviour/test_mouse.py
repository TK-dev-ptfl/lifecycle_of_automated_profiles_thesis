"""Atomic tests for the cursor primitives.

Each asserts one property of human pointer motion that its absence would make
detectable - a straight path, an instant jump, a zero-length button press, a click
that always lands dead centre.
"""
from __future__ import annotations

import math

import pytest

from app.behaviour.primitives import mouse
from tests.behaviour.recorders import RecordingMouse, RecordingSleeper

START = (100.0, 100.0)
END = (900.0, 600.0)


def _distance(a, b) -> float:
    return math.dist(a, b)


def _max_deviation_from_straight_line(path, start, end) -> float:
    """Largest perpendicular distance from any sampled point to the straight line
    between start and end - i.e. how bowed the path is."""
    (x0, y0), (x1, y1) = start, end
    span = _distance(start, end)
    worst = 0.0
    for px, py in path:
        # Cross product magnitude over the base length is the perpendicular gap.
        gap = abs((x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)) / span
        worst = max(worst, gap)
    return worst


# --- bezier_path -------------------------------------------------------------

def test_path_starts_moving_toward_the_target_and_ends_exactly_on_it():
    path = mouse.bezier_path(START, END, steps=20)
    assert len(path) == 20
    # Ending anywhere but the target would mean the caller has to correct, and a
    # correction it did not ask for.
    assert path[-1] == END


def test_path_is_curved_not_a_straight_line():
    """A perfectly straight travel path is the single most obvious pointer tell:
    hands do not move in straight lines."""
    path = mouse.bezier_path(START, END, steps=40)
    bow = _max_deviation_from_straight_line(path, START, END)
    assert bow > 5.0, f"path is essentially straight (max deviation {bow:.2f}px)"


def test_two_paths_between_the_same_points_differ():
    """A fixed curve would be as recognisable as a fixed straight line."""
    a = mouse.bezier_path(START, END, steps=30)
    b = mouse.bezier_path(START, END, steps=30)
    assert a != b


def test_zero_length_move_does_not_divide_by_zero():
    path = mouse.bezier_path(START, START, steps=5)
    assert path == [START] * 5


# --- steps_for_distance ------------------------------------------------------

def test_step_count_grows_with_distance_but_stays_bounded():
    short = mouse.steps_for_distance(20)
    long = mouse.steps_for_distance(2000)
    assert short >= 8, "even a tiny adjustment must not be a single teleport"
    assert short < long
    assert long <= 60, "a long sweep must not become hundreds of browser round trips"


# --- move_to -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_move_emits_many_points_and_pauses_between_them():
    recorder, sleeper = RecordingMouse(), RecordingSleeper()
    path = await mouse.move_to(recorder, START, END, sleeper=sleeper)

    assert len(recorder.path) == len(path) > 8
    assert recorder.path[-1] == END
    # Without a gap per sample the whole path is delivered in one tick: the right
    # shape, but travelling instantaneously.
    assert len(sleeper.waits) == len(path)
    assert all(w > 0 for w in sleeper.waits)


# --- drag --------------------------------------------------------------------

@pytest.mark.asyncio
async def test_drag_presses_moves_then_releases_in_that_order():
    recorder, sleeper = RecordingMouse(), RecordingSleeper()
    await mouse.drag(recorder, START, END, sleeper=sleeper)

    kinds = recorder.kinds
    assert kinds[0] == "move", "must be positioned before the button goes down"
    assert kinds[1] == "down"
    assert kinds[-1] == "up"
    assert kinds.count("down") == 1 and kinds.count("up") == 1
    # Everything between the press and the release is travel.
    assert set(kinds[2:-1]) == {"move"}


@pytest.mark.asyncio
async def test_drag_settles_before_pressing_and_before_releasing():
    """A gesture that takes exactly as long as its travel has no hand in it."""
    recorder, sleeper = RecordingMouse(), RecordingSleeper()
    path = await mouse.drag(recorder, START, END, sleeper=sleeper)
    # One pause per path sample, plus the press and release settles.
    assert len(sleeper.waits) == len(path) + 2


# --- click_at ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_click_holds_the_button_down_for_a_measurable_moment():
    recorder, sleeper = RecordingMouse(), RecordingSleeper()
    await mouse.click_at(recorder, (500.0, 400.0), sleeper=sleeper)

    assert recorder.kinds == ["move", "down", "up"]
    # move-settle, hold, and nothing else: a zero-length press is visible to
    # anything watching pointer events.
    assert len(sleeper.waits) == 2
    assert all(w > 0 for w in sleeper.waits)


# --- landing_point -----------------------------------------------------------

def test_landing_point_stays_inside_the_box():
    box = {"x": 100.0, "y": 200.0, "width": 180.0, "height": 40.0}
    for _ in range(300):
        x, y = mouse.landing_point(box)
        assert box["x"] <= x <= box["x"] + box["width"]
        assert box["y"] <= y <= box["y"] + box["height"]


def test_landing_point_is_scattered_not_the_exact_centre():
    """Clicking the centre pixel of every target is a strong signal."""
    box = {"x": 0.0, "y": 0.0, "width": 200.0, "height": 50.0}
    points = {mouse.landing_point(box) for _ in range(50)}
    assert len(points) > 40, "landing points are barely varying"
    assert (100.0, 25.0) not in points


# --- overshoot_point ---------------------------------------------------------

def test_long_travel_overshoots_past_the_target():
    """Fast pointing motions are ballistic: they fly past and correct back."""
    target, origin = (900.0, 300.0), (100.0, 300.0)
    past = mouse.overshoot_point(target, origin)
    assert past is not None
    # Beyond the target, still on the same side.
    assert past[0] > target[0]


def test_short_travel_does_not_overshoot():
    """Overshooting a 30px adjustment is not something a hand does."""
    assert mouse.overshoot_point((120.0, 300.0), (100.0, 300.0)) is None
