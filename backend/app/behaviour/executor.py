"""Runs goals against an environment, with a profile deciding how.

This is the only place the three halves meet: WHAT (goals), WHO (profile), WHERE
(environment). Everything motor lives in primitives/, everything about composing
motor acts lives in this file's handlers, and neither knows which environment it
is driving.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from app.behaviour.environment import (
    Box, CollectedItem, Environment, Observation, Point, Target,
)
from app.behaviour.goals import (
    ClickOn, Dwell, Goal, ReadFeed, ScrollTo, TypeInto, WaitFor, Wander,
)
from app.behaviour.primitives import keyboard as keyboard_primitives
from app.behaviour.primitives import mouse as mouse_primitives
from app.behaviour.primitives import scroll as scroll_primitives
from app.behaviour.primitives.timing import lognormal_delay, reading_time_s
from app.behaviour.profile import AVERAGE, BehaviourProfile

Logger = Callable[[str], None]


class GoalFailed(RuntimeError):
    """A goal could not be achieved. Carries the goal so a caller can report
    which intention failed rather than which coordinate did."""

    def __init__(self, goal: Goal, reason: str) -> None:
        super().__init__(f"{type(goal).__name__}: {reason}")
        self.goal = goal
        self.reason = reason


@dataclass
class Actor:
    """A simulated person acting in an environment.

    Holds the one piece of state neither the environment nor the profile has: where
    the pointer currently is. Without it every move would have to start by
    teleporting to a known origin, which is itself the artefact being avoided.
    """

    env: Environment
    profile: BehaviourProfile = AVERAGE
    log: Logger = lambda _m: None
    at: Point = field(default=(0.0, 0.0))
    # Everything ReadFeed has gathered this session, in the order it was read.
    collected: list[dict] = field(default_factory=list)
    # False until the cursor has come onto the page. See _ensure_entered.
    entered: bool = False

    def __post_init__(self) -> None:
        viewport = self.env.viewport()
        if self.at == (0.0, 0.0):
            # Starting in the corner is a tell; start somewhere unremarkable.
            self.at = (
                random.uniform(0.2, 0.8) * viewport.width,
                random.uniform(0.2, 0.8) * viewport.height,
            )
        else:
            # A caller that says where the cursor is knows it is already there.
            self.entered = True

    # --- shared motor acts -------------------------------------------------
    async def _pause(self, median_s: float) -> float:
        seconds = lognormal_delay(median_s, cap_s=median_s * 8)
        await self.env.sleep(seconds)
        return seconds

    def _clamp(self, point: Point, margin: float = 3.0) -> Point:
        viewport = self.env.viewport()
        return (
            min(max(point[0], margin), viewport.width - margin),
            min(max(point[1], margin), viewport.height - margin),
        )

    async def _ensure_entered(self) -> None:
        """Brings the cursor onto the page the way it arrives in a real session.

        A page that has just loaded has had no pointer over it: the person was up
        in the address bar, or on a link in the previous page, so the first thing
        the page sees is a cursor coming in across its top edge. A first
        mousemove in the middle of the viewport, out of nowhere, is a pointer
        that was placed rather than moved.
        """
        if self.entered:
            return
        self.entered = True
        viewport = self.env.viewport()
        self.at = (random.uniform(0.25, 0.75) * viewport.width, random.uniform(1.0, 6.0))
        await self.env.mouse.move(self.at[0], self.at[1])

    async def _move_along(self, to: Point, target_size: float) -> None:
        """One continuous movement from where the cursor is to `to`."""
        for x, y, wait in mouse_primitives.human_path(
            self.at, to, curviness=self.profile.path_curviness, target_size=target_size,
        ):
            # The bow of a path near an edge can carry it a few pixels past it;
            # clamped, so the pointer never leaves the page mid-gesture.
            x, y = self._clamp((x, y), margin=1.0)
            await self.env.sleep(wait)
            await self.env.mouse.move(x, y)
        self.at = to

    async def _travel(self, to: Point, target_size: float = 40.0) -> None:
        """Gets the cursor to `to` as an aimed movement.

        Long aimed movements are often two: a fast primary one that lands near
        the target, then a small corrective one onto it. Making every long trip
        in one perfectly aimed stroke is the more mechanical option.
        """
        await self._ensure_entered()
        to = self._clamp(to)
        distance = ((to[0] - self.at[0]) ** 2 + (to[1] - self.at[1]) ** 2) ** 0.5
        if distance > 260 and random.random() < 0.45:
            short = random.uniform(0.02, 0.06)
            near = self._clamp((
                to[0] - (to[0] - self.at[0]) * short + random.uniform(-6, 6),
                to[1] - (to[1] - self.at[1]) * short + random.uniform(-6, 6),
            ))
            await self._move_along(near, target_size * 2)
            await self.env.sleep(random.uniform(0.04, 0.14))
        await self._move_along(to, target_size)

    async def _idle(self, seconds: float, region: Optional[Box] = None) -> None:
        """Lets `seconds` pass the way they pass with a hand on the mouse.

        Mostly the cursor rests - people do keep still while reading - but now
        and then it is nudged, and occasionally moved somewhere else inside
        `region` (by default the middle of the screen). How often it moves is
        the profile's restlessness. A pointer frozen through every wait, that
        only ever moves in order to act, is the pattern this replaces.
        """
        viewport = self.env.viewport()
        if region is None:
            region = Box(viewport.width * 0.15, viewport.height * 0.15,
                         viewport.width * 0.7, viewport.height * 0.7)
        deadline = self.env.now() + max(0.0, seconds)
        while (left := deadline - self.env.now()) > 0.05:
            roll = random.random()
            if roll >= self.profile.restlessness:
                await self.env.sleep(min(left, lognormal_delay(0.9, spread=0.6, cap_s=4.0)))
            elif roll >= self.profile.restlessness * 0.3:
                nudge = self._clamp((self.at[0] + random.uniform(-16, 16),
                                     self.at[1] + random.uniform(-10, 10)))
                await self._move_along(nudge, 30.0)
                await self.env.sleep(random.uniform(0.1, 0.5))
            else:
                await self._travel((region.x + random.random() * region.width,
                                    region.y + random.random() * region.height), 80.0)
                await self.env.sleep(random.uniform(0.2, 0.8))

    async def _trace(self, start: Point, end: Point, seconds: float) -> None:
        """Follows a line of text with the cursor over `seconds`: slow, nearly
        straight, and paced by reading rather than by aiming."""
        await self._travel(start, 60.0)
        path = mouse_primitives.bezier_path(
            self.at, end, max(8, int(seconds / 0.03)), curviness=0.06,
        )
        # Tracking by eye is not a rail either: the hand drifts a pixel or two
        # off the line and back as it goes.
        wobble = 0.0
        for i, (x, y) in enumerate(path):
            wobble = 0.8 * wobble + random.gauss(0.0, 0.9)
            if i == len(path) - 1:
                wobble = 0.0
            await self.env.sleep(seconds / len(path) * random.uniform(0.6, 1.4))
            await self.env.mouse.move(*self._clamp((x, y + wobble), margin=1.0))
        self.at = end

    async def _scroll(self, notches: int) -> None:
        await scroll_primitives.wheel(_ScrollShim(self.env), notches, sleeper=self.env.sleep)
        # A wheel scroll animates on after the last notch: what is on screen has
        # not settled until it stops, and nobody reads mid-glide either.
        await self.env.sleep(max(0.3, lognormal_delay(0.55 * self.profile.hesitancy, cap_s=3.0)))

    async def _click_here(self) -> None:
        await self._pause(self.profile.settle_s())
        await self.env.mouse.down()
        await self._pause(self.profile.settle_s() * 0.8)
        await self.env.mouse.up()

    async def _resolve(self, goal: Goal, target: Target, timeout_s: Optional[float] = None) -> Observation:
        """Waits for a target to become actionable, polling rather than assuming.

        Patience comes from the profile, so an impatient persona gives up on a
        slow page sooner - which is behaviour, not a bug.
        """
        budget = timeout_s if timeout_s is not None else self.profile.patience_s
        waited = 0.0
        step = 0.25
        while True:
            observation = await self.env.observe(target)
            if observation.actionable:
                return observation
            if waited >= budget:
                raise GoalFailed(
                    goal,
                    f"{target} never became actionable within {budget:.0f}s "
                    f"(exists={observation.exists}, visible={observation.visible})",
                )
            await self.env.sleep(step)
            waited += step

    # --- goal handlers -----------------------------------------------------
    async def wander(self, goal: Wander) -> int:
        """Moves around the page without acting on anything.

        Hovering, not dragging: pressing the button at random points selects
        swathes of text, starts drags on images and links, and focuses whatever
        input it lands on - all of it visible, and none of it what an idle hand
        does.
        """
        viewport = self.env.viewport()
        count = goal.count if goal.count is not None else random.randint(*self.profile.wander_range)
        for _ in range(max(0, count)):
            await self._travel((
                random.uniform(0.08, 0.92) * viewport.width,
                random.uniform(0.08, 0.92) * viewport.height,
            ), 120.0)
            await self._idle(lognormal_delay(self.profile.think_s(), cap_s=4.0))
        self.log(f"wandered {count} time(s) - {goal.reason}")
        return count

    async def dwell(self, goal: Dwell) -> float:
        median = goal.seconds if goal.seconds is not None else self.profile.read_s()
        seconds = lognormal_delay(median, cap_s=median * 8)
        await self._ensure_entered()
        await self._idle(seconds)
        self.log(f"dwelt {seconds:.1f}s - {goal.reason}")
        return seconds

    async def scroll_to(self, goal: ScrollTo) -> None:
        observation = await self.env.observe(goal.target)
        if not observation.exists:
            raise GoalFailed(goal, f"{goal.target} does not exist")

        await self._ensure_entered()
        viewport = self.env.viewport()
        for _ in range(40):
            observation = await self.env.observe(goal.target)
            if observation.actionable:
                # Centred enough to act on, not pinned to an exact offset.
                assert observation.box is not None
                if 0.1 * viewport.height < observation.box.centre[1] < 0.9 * viewport.height:
                    self.log(f"scrolled {goal.target} into view")
                    return
            direction = 1 if (observation.box is None or observation.box.y > 0) else -1
            await scroll_primitives.wheel(
                _ScrollShim(self.env), direction * 2, sleeper=self.env.sleep
            )
            await self._pause(0.25 * self.profile.hesitancy)
        raise GoalFailed(goal, f"could not bring {goal.target} into view")

    async def click_on(self, goal: ClickOn) -> Point:
        observation = await self._resolve(goal, goal.target)
        assert observation.box is not None
        point = _landing_point(observation.box, self.profile.aim_scatter)
        viewport = self.env.viewport()
        if not (0 <= point[1] <= viewport.height and 0 <= point[0] <= viewport.width):
            # Travel is clamped to the viewport, so going ahead would press
            # whatever sits at the edge instead - a silent misclick.
            raise GoalFailed(goal, f"{goal.target} is off screen at ({point[0]:.0f}, {point[1]:.0f}); ScrollTo it first")
        size = max(8.0, min(observation.box.width, observation.box.height))

        await self._ensure_entered()
        if random.random() < self.profile.overshoot_chance:
            past = mouse_primitives.overshoot_point(point, self.at)
            if past is not None:
                await self._move_along(self._clamp(past), size * 2)

        await self._travel(point, size)
        await self._pause(self.profile.think_s())
        await self._click_here()
        self.log(f"clicked {goal.target} at ({point[0]:.0f}, {point[1]:.0f})")
        return point

    async def type_into(self, goal: TypeInto) -> list[str]:
        await self.click_on(ClickOn(goal.target))
        await self._pause(self.profile.think_s())

        sent = await keyboard_primitives.type_text(
            self.env.keyboard,
            goal.text,
            words_per_minute=self.profile.typing_wpm,
            typo_chance=self.profile.typo_chance,
            hold_ms=self.profile.key_hold_ms,
            sleeper=self.env.sleep,
        )
        corrections = sent.count("Backspace")
        self.log(
            f"typed {len(goal.text)} characters into {goal.target}"
            + (f", corrected {corrections}" if corrections else "")
        )
        await self._pause(self.profile.think_s() * 0.7)

        if goal.verify:
            observation = await self.env.observe(goal.target)
            if observation.value != goal.text:
                raise GoalFailed(
                    goal,
                    f"{goal.target} holds {observation.value!r}, expected {goal.text!r} - "
                    "typing did not register",
                )
        return sent

    async def wait_for(self, goal: WaitFor) -> Observation:
        observation = await self._resolve(goal, goal.target, goal.timeout_s)
        self.log(f"{goal.target} is ready")
        return observation

    async def read_feed(self, goal: ReadFeed) -> list[dict]:
        """Work down a feed, reading each post before moving on.

        The shape of this is the behaviour, and it is deliberately not "query all
        the items and return them":

          - posts are read top to bottom, and only once they are ON SCREEN in
            the part of the viewport a person reads from. Reading something that
            was never scrolled into view is the single clearest sign nothing
            human is driving, because a person cannot read what they have not
            looked at.
          - the page moves by wheel, a few notches at a time, just far enough to
            bring the next post up, then stops while it is read. That stop-start
            rhythm is what reading looks like from the page's side.
          - each post is dwelt on for a time proportional to how much it says
            (reading_time_s), so a one-line post costs a glance and a long one
            costs real seconds - with the hand alive meanwhile.
          - scrolling continues only while new items keep appearing; a feed that
            stops yielding them ends the goal instead of scrolling forever.

        Returns the items read, and also appends them to self.collected so a
        caller that ran a whole goal list still gets at them.
        """
        await self._ensure_entered()
        seen: set[str] = set()
        read_items: list[dict] = []
        barren = 0
        column: Optional[Box] = None

        while len(read_items) < goal.want and barren < goal.max_barren_scrolls:
            viewport = self.env.viewport()
            items = await self.env.collect(goal.schema.item, goal.schema.fields)
            unread = [i for i in items if i.visible and i.key() and i.key() not in seen]

            readable = next(
                (i for i in unread
                 if i.box.y < viewport.height * 0.7
                 and i.box.y + i.box.height > viewport.height * 0.2),
                None,
            )
            if readable is not None:
                seen.add(readable.key())
                column = readable.box
                read_items.append(await self._read_item(readable))
                barren = 0
                continue

            # Nothing to read where the eyes are. A post peeking in at the
            # bottom gets brought up to reading height; otherwise the page
            # moves on by most of a screen.
            below = next((i for i in unread if i.box.y >= viewport.height * 0.7), None)
            if below is not None:
                distance = below.box.y - viewport.height * random.uniform(0.12, 0.3)
            else:
                distance = viewport.height * random.uniform(0.55, 0.8)
                barren += 1
            if column is not None and not (column.x <= self.at[0] <= column.x + column.width):
                # The wheel scrolls whatever is under the cursor, and people
                # scroll with it over what they are reading.
                await self._travel((column.x + column.width * random.uniform(0.3, 0.7),
                                    viewport.height * random.uniform(0.35, 0.65)), 120.0)
            await self._scroll(max(1, round(distance / scroll_primitives.NOTCH_PX)))

        self.collected.extend(read_items)
        self.log(f"read {len(read_items)} item(s) from {goal.schema.item}")
        return read_items

    async def _read_item(self, item: CollectedItem) -> dict:
        """Look at one post: bring the cursor near it (or not), and read for as
        long as it takes, following the text or resting while that happens."""
        assert item.box is not None
        box, viewport = item.box, self.env.viewport()
        # The visible part of the post: the hand stays over what the eyes are on.
        top, bottom = max(box.y, 0.0), min(box.y + box.height, viewport.height)
        region = Box(box.x + box.width * 0.05, top, box.width * 0.9, max(bottom - top, 1.0))

        body = " ".join(str(v) for v in item.fields.values())
        seconds = reading_time_s(body) * self.profile.hesitancy

        if random.random() < self.profile.reads_with_cursor:
            # Line by line through the upper part of the post, where its text
            # is - the middle of a tall post can be an image or past the end.
            lines = max(1, min(4, len(body) // 70 + 1))
            per_line = seconds / lines
            y = top + (bottom - top) * random.uniform(0.15, 0.35)
            for _ in range(lines):
                start = (box.x + box.width * random.uniform(0.08, 0.18), y)
                end = (box.x + box.width * random.uniform(0.6, 0.9), y + random.uniform(-3, 3))
                await self._trace(self._clamp(start), self._clamp(end), per_line * 0.8)
                await self.env.sleep(per_line * 0.2)
                y = min(bottom - 4, y + random.uniform(18, 26))
        else:
            if random.random() < 0.7 or not region.contains(self.at):
                await self._travel((
                    box.x + box.width * random.uniform(0.15, 0.6),
                    top + (bottom - top) * random.uniform(0.15, 0.5),
                ), max(40.0, box.width * 0.4))
            await self._idle(seconds, region)

        preview = (item.fields.get("body") or body)[:48]
        self.log(f"read item {item.index} in {seconds:.1f}s: {preview!r}")
        return dict(item.fields)

    # --- the loop ----------------------------------------------------------
    async def pursue(self, goals: Iterable[Goal]) -> None:
        handlers = {
            Wander: self.wander,
            Dwell: self.dwell,
            ScrollTo: self.scroll_to,
            ClickOn: self.click_on,
            TypeInto: self.type_into,
            WaitFor: self.wait_for,
            ReadFeed: self.read_feed,
        }
        for goal in goals:
            handler = handlers.get(type(goal))
            if handler is None:
                raise GoalFailed(goal, "no handler for this goal type")
            await handler(goal)


class _ScrollShim:
    """Adapts an Environment to what the scroll primitive expects.

    The primitive predates the Environment port and speaks evaluate(); rather than
    widen the port with a browser-shaped method, this translates. Small enough to
    be worth keeping the port clean for.
    """

    def __init__(self, env: Environment) -> None:
        self.env = env
        self.mouse = env.mouse
        self.keyboard = env.keyboard

    @property
    def viewport_size(self) -> dict:
        box = self.env.viewport()
        return {"width": box.width, "height": box.height}

    async def evaluate(self, expression: str, arg=None):
        await self.env.scroll_by(float(arg or 0))


def _landing_point(box: Box, scatter: float) -> Point:
    """Somewhere inside the box, scattered by the profile's aim. Deliberately not
    the centre - see BehaviourProfile.aim_scatter."""
    return mouse_primitives.landing_point(box.as_dict(), bias=scatter)
