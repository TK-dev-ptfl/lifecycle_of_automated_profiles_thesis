"""Simulated human interaction, in four layers that can each be used alone.

    profile.py       WHO   - the variables. Typing speed, hesitancy, aim scatter,
                             patience. derive_for(identity) gives every account a
                             stable, distinct persona.
    goals.py         WHAT  - declarative intentions: ClickOn, TypeInto, ScrollTo,
                             Wander, Dwell, WaitFor. No coordinates, no timings,
                             no environment.
    environment.py   WHERE - the port. Everything the layer is allowed to know
                             about the outside world: a viewport, a way to observe
                             a Target, scroll, sleep, a mouse and a keyboard.
    executor.py      HOW   - an Actor that pursues goals in an environment, with a
                             profile deciding the manner.

    primitives/            one physical act each (paths, drags, clicks, keystroke
                           rhythm, wheel notches), testable in isolation.
    algorithms/            older compositions kept for the email pipeline.
    adapters/              SimulatedEnvironment (in-memory, virtual clock) and
                           PlaywrightEnvironment (a real page).

Pointing this at a new site means writing a list of goals and choosing a profile.
No motor behaviour changes - which is exactly what the simulator is there to
prove, since the same goal list runs against it and against a real browser.

Why any of it: thesis 2.2.3 - instant, pixel-perfect, evenly-timed input is one of
the cheapest automation signals there is. A real cursor accelerates, bows,
overshoots and drifts; real typing has uneven gaps and the occasional correction;
a real person pauses before committing to anything.
"""
from app.behaviour.environment import Box, Environment, Observation, Target
from app.behaviour.executor import Actor, GoalFailed
from app.behaviour.goals import ClickOn, Dwell, Goal, ScrollTo, TypeInto, WaitFor, Wander
from app.behaviour.profile import AVERAGE, BRISK, CAREFUL, BehaviourProfile, derive_for

__all__ = [
    "Actor", "GoalFailed",
    "Box", "Environment", "Observation", "Target",
    "ClickOn", "Dwell", "Goal", "ScrollTo", "TypeInto", "WaitFor", "Wander",
    "BehaviourProfile", "derive_for", "AVERAGE", "BRISK", "CAREFUL",
]
