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

from app.behaviour.environment import Box, Environment, Observation, Point, Target
from app.behaviour.goals import ClickOn, Dwell, Goal, ScrollTo, TypeInto, WaitFor, Wander
from app.behaviour.primitives import keyboard as keyboard_primitives
from app.behaviour.primitives import mouse as mouse_primitives
from app.behaviour.primitives import scroll as scroll_primitives
from app.behaviour.primitives.timing import lognormal_delay
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

    def __post_init__(self) -> None:
        viewport = self.env.viewport()
        if self.at == (0.0, 0.0):
            # Starting in the corner is a tell; start somewhere unremarkable.
            self.at = (
                random.uniform(0.2, 0.8) * viewport.width,
                random.uniform(0.2, 0.8) * viewport.height,
            )

    # --- shared motor acts -------------------------------------------------
    async def _pause(self, median_s: float) -> float:
        seconds = lognormal_delay(median_s, cap_s=median_s * 8)
        await self.env.sleep(seconds)
        return seconds

    async def _travel(self, to: Point) -> None:
        path = mouse_primitives.bezier_path(
            self.at, to,
            mouse_primitives.steps_for_distance(
                ((to[0] - self.at[0]) ** 2 + (to[1] - self.at[1]) ** 2) ** 0.5
            ),
            curviness=self.profile.path_curviness,
        )
        for point in path:
            await self.env.mouse.move(point[0], point[1])
            await self.env.sleep(random.uniform(0.004, 0.016))
        self.at = to

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
        viewport = self.env.viewport()
        count = goal.count if goal.count is not None else random.randint(*self.profile.wander_range)
        for _ in range(max(0, count)):
            destination = (
                random.uniform(0.08, 0.92) * viewport.width,
                random.uniform(0.08, 0.92) * viewport.height,
            )
            # A press-move-release, not just a move: dragging is what a hand does
            # while reading - selecting a little text, fidgeting.
            await self.env.mouse.move(self.at[0], self.at[1])
            await self._pause(self.profile.settle_s())
            await self.env.mouse.down()
            await self._travel(destination)
            await self._pause(self.profile.settle_s())
            await self.env.mouse.up()
            await self._pause(self.profile.think_s())
        self.log(f"wandered {count} time(s) - {goal.reason}")
        return count

    async def dwell(self, goal: Dwell) -> float:
        median = goal.seconds if goal.seconds is not None else self.profile.read_s()
        seconds = await self._pause(median)
        self.log(f"dwelt {seconds:.1f}s - {goal.reason}")
        return seconds

    async def scroll_to(self, goal: ScrollTo) -> None:
        observation = await self.env.observe(goal.target)
        if not observation.exists:
            raise GoalFailed(goal, f"{goal.target} does not exist")

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

        if random.random() < self.profile.overshoot_chance:
            past = mouse_primitives.overshoot_point(point, self.at)
            if past is not None:
                await self._travel(past)

        await self._travel(point)
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

    # --- the loop ----------------------------------------------------------
    async def pursue(self, goals: Iterable[Goal]) -> None:
        handlers = {
            Wander: self.wander,
            Dwell: self.dwell,
            ScrollTo: self.scroll_to,
            ClickOn: self.click_on,
            TypeInto: self.type_into,
            WaitFor: self.wait_for,
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
