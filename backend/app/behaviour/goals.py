"""Goals: what to achieve, declared separately from how a hand achieves it.

A goal names an intention and a target. It carries no coordinates, no selectors
syntax, no timing, and no idea which environment it will run in - all of that is
supplied at execution time by the Environment and the BehaviourProfile.

That separation is the point. Pointing this at a new site means writing a list of
goals and picking a profile; it does not mean touching a single line of motor
behaviour. The same list runs unchanged against the simulator and a real page.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from app.behaviour.environment import Target


@dataclass(frozen=True)
class Wander:
    """Drift around aimlessly for a moment.

    Not decoration: arriving somewhere and moving in one straight line to the
    single control you intend to use is a strong signal. count=None means "take
    it from the profile", which is the usual case.
    """

    count: Optional[int] = None
    reason: str = "looking around"


@dataclass(frozen=True)
class Dwell:
    """Pause as if reading or deciding. Scaled by the profile's hesitancy."""

    seconds: Optional[float] = None
    reason: str = "reading"


@dataclass(frozen=True)
class ScrollTo:
    """Bring a target into view, the way a wheel does - in notches, with an
    overshoot and a correction, not one jump."""

    target: Target


@dataclass(frozen=True)
class ClickOn:
    """Travel to a target and click it."""

    target: Target


@dataclass(frozen=True)
class TypeInto:
    """Click into a field and type a value, then verify the field took it.

    `verify` exists because per-key typing can be swallowed by a field that
    re-renders mid-stream, and discovering that at submit time is far worse than
    discovering it here.
    """

    target: Target
    text: str
    verify: bool = True


@dataclass(frozen=True)
class WaitFor:
    """Wait for a target to become actionable, up to the profile's patience."""

    target: Target
    timeout_s: Optional[float] = None


Goal = Union[Wander, Dwell, ScrollTo, ClickOn, TypeInto, WaitFor]
