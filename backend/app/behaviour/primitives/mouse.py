"""Cursor primitives: paths, moves, drags, clicks.

The shared idea is that a real cursor is driven by a hand, so it never travels in
a straight line at constant speed, never lands exactly on a target's centre, and
never starts or stops instantly. Each function here produces one such motion and
nothing else; combining them into something purposeful is the algorithms' job.
"""
from __future__ import annotations

import random
from typing import Optional

from app.behaviour.primitives.timing import Sleeper, _real_sleep, pause
from app.behaviour.protocols import MouseLike

Point = tuple[float, float]


def bezier_path(start: Point, end: Point, steps: int, curviness: float = 0.22) -> list[Point]:
    """A cubic Bézier from start to end, sampled at `steps` points.

    Two control points are offset perpendicular to the straight line, which is
    what gives the path its bow. The offsets are random per call and can fall on
    either side, so repeated trips between the same two points never retrace the
    same arc - a fixed curve would be as recognisable as a straight line.

    Returned points are in order and the last one is exactly `end`; the caller is
    expected to add its own overshoot or landing error if it wants any.
    """
    steps = max(2, steps)
    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    distance = (dx * dx + dy * dy) ** 0.5
    if distance == 0:
        return [end] * steps

    # Unit normal to the direction of travel.
    nx, ny = -dy / distance, dx / distance
    bow = distance * curviness

    def control(at: float) -> Point:
        offset = random.uniform(-bow, bow)
        return (x0 + dx * at + nx * offset, y0 + dy * at + ny * offset)

    c1, c2 = control(0.33), control(0.66)

    path: list[Point] = []
    for i in range(steps):
        t = (i + 1) / steps
        u = 1 - t
        # Standard cubic Bézier basis.
        bx = u**3 * x0 + 3 * u**2 * t * c1[0] + 3 * u * t**2 * c2[0] + t**3 * x1
        by = u**3 * y0 + 3 * u**2 * t * c1[1] + 3 * u * t**2 * c2[1] + t**3 * y1
        path.append((bx, by))
    path[-1] = end
    return path


def steps_for_distance(distance: float) -> int:
    """How many intermediate points a move of this length should be made of.

    Longer travel gets more samples, but sub-linearly - a cursor crossing the
    screen is not sampled a thousand times. Bounded at both ends so a tiny
    adjustment still takes more than one jump (instant teleports are the tell)
    and a long sweep does not turn into hundreds of round trips to the browser.
    """
    return int(max(8, min(60, distance ** 0.55)))


async def move_to(
    mouse: MouseLike,
    start: Point,
    end: Point,
    *,
    sleeper: Sleeper = _real_sleep,
) -> list[Point]:
    """Moves the cursor along a curved path and returns the path it took.

    Playwright's own `steps=` interpolates linearly, so it is used one segment at
    a time here rather than for the whole trip - the curve has to come from us.
    """
    path = bezier_path(start, end, steps_for_distance(_distance(start, end)))
    for point in path:
        await mouse.move(point[0], point[1])
        # A few milliseconds between samples. Without this the whole path is
        # delivered in one tick and the motion is instantaneous in wall time
        # even though its shape is right.
        await sleeper(random.uniform(0.004, 0.016))
    return path


async def drag(
    mouse: MouseLike,
    start: Point,
    end: Point,
    *,
    sleeper: Sleeper = _real_sleep,
) -> list[Point]:
    """Press at start, move along a curve, release at end.

    A drag is not a move with the button held: the press and release each need
    their own settling pause, or the whole gesture takes exactly as long as the
    travel and reads as synthetic.
    """
    await mouse.move(start[0], start[1])
    await pause(0.09, spread=0.4, cap_s=0.6, sleeper=sleeper)
    await mouse.down()
    path = await move_to(mouse, start, end, sleeper=sleeper)
    await pause(0.07, spread=0.4, cap_s=0.5, sleeper=sleeper)
    await mouse.up()
    return path


async def click_at(
    mouse: MouseLike,
    point: Point,
    *,
    sleeper: Sleeper = _real_sleep,
) -> None:
    """Press and release in place, with a hold in between.

    The hold is the point of this existing separately from Playwright's click():
    a real button press lasts tens of milliseconds, and a zero-length one is
    visible to anything watching pointer events.
    """
    await mouse.move(point[0], point[1])
    await pause(0.08, spread=0.4, cap_s=0.5, sleeper=sleeper)
    await mouse.down()
    await pause(0.065, spread=0.35, cap_s=0.4, sleeper=sleeper)
    await mouse.up()


def landing_point(box: dict, *, bias: float = 0.34) -> Point:
    """A point inside an element's bounding box to aim at.

    Deliberately not the centre. Clicking the exact centre pixel of every target
    is a strong signal; a hand lands somewhere in the middle region, scattered.
    `bias` is the fraction of the box's size the landing point may wander from
    the centre - 0.34 keeps it comfortably inside while never being predictable.

    Takes Playwright's bounding_box() dict shape: x, y, width, height.
    """
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    return (
        cx + random.uniform(-1, 1) * box["width"] * bias,
        cy + random.uniform(-1, 1) * box["height"] * bias,
    )


def overshoot_point(target: Point, from_point: Point, amount: float = 0.1) -> Optional[Point]:
    """Where the cursor flies slightly past the target before settling back, or
    None when the trip is too short to overshoot plausibly.

    Fast pointing motions routinely overshoot and correct - it is a consequence
    of moving ballistically rather than tracking. A cursor that stops dead on
    target every single time is doing something a hand cannot.
    """
    distance = _distance(from_point, target)
    if distance < 120:
        return None
    dx = (target[0] - from_point[0]) / distance
    dy = (target[1] - from_point[1]) / distance
    past = distance * random.uniform(amount * 0.5, amount)
    return (target[0] + dx * past, target[1] + dy * past)


def _distance(a: Point, b: Point) -> float:
    return ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
