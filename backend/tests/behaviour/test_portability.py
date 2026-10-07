"""The portability claim, made concrete.

The point of the Environment port is that a flow is written once as goals, and
moving it to a new site means supplying different variables and goals - not
touching any motor behaviour. These tests build a Reddit-shaped world in the
simulator and run a flow through it, which is the same flow and the same executor
that a real page would get.

They also pin the properties that make that true: the goal list contains no
coordinates or timings, and the identical list runs against two completely
different worlds.
"""
from __future__ import annotations

import pytest

from app.behaviour.adapters.simulated import SimElement, SimulatedEnvironment
from app.behaviour.environment import Target
from app.behaviour.executor import Actor
from app.behaviour.goals import ClickOn, Dwell, TypeInto, WaitFor, Wander
from app.behaviour.profile import derive_for

# The ONLY site-specific things. Swapping these for a different site's - and
# nothing else - is what "transfer it by adding variables and goals" means.
SIGNUP_BUTTON = Target("#signup-button", "the signup button")
SIGNUP_DIALOG = Target('[role="dialog"]', "the signup dialog")
EMAIL_FIELD = Target('input[name="email"]', "the email field")
CONTINUE_BUTTON = Target("#continue", "the continue button")


def reddit_signup_flow(email: str) -> list:
    """The flow as pure intent: no coordinates, no timings, no selectors syntax
    beyond the targets, and nothing about which environment it runs in."""
    return [
        Dwell(reason="taking in the page"),
        Wander(reason="not walking straight to the one button we want"),
        ClickOn(SIGNUP_BUTTON),
        WaitFor(SIGNUP_DIALOG),
        TypeInto(EMAIL_FIELD, email),
        ClickOn(CONTINUE_BUTTON),
    ]


def fake_reddit() -> SimulatedEnvironment:
    """A world shaped like Reddit's signup, with the dialog initially absent -
    so WaitFor has something real to wait for."""
    env = SimulatedEnvironment(
        [
            SimElement("#signup-button", x=1180, y=16, width=110, height=32),
        ]
    )

    original_up = env.mouse.up

    async def up_then_open_dialog(**kwargs):
        await original_up(**kwargs)
        # Clicking signup is what makes the dialog and its contents exist, the
        # same way it does on the real site.
        if env.clicked and env.clicked[-1] == "#signup-button" and '[role="dialog"]' not in env.elements:
            env.elements['[role="dialog"]'] = SimElement(
                '[role="dialog"]', x=450, y=250, width=460, height=380, kind="text"
            )
            env.elements['input[name="email"]'] = SimElement(
                'input[name="email"]', x=480, y=380, width=400, height=44, kind="input"
            )
            env.elements["#continue"] = SimElement(
                "#continue", x=480, y=520, width=400, height=48
            )

    env.mouse.up = up_then_open_dialog  # type: ignore[method-assign]
    return env


@pytest.mark.asyncio
async def test_a_reddit_shaped_flow_runs_end_to_end_in_the_simulator():
    email = "alexsmith.skating705672@tuta.com"
    env = fake_reddit()
    trace: list[str] = []

    await Actor(env=env, profile=derive_for("identity-1"), log=trace.append).pursue(
        reddit_signup_flow(email)
    )

    # Outcomes, not calls.
    assert env.clicked[-1] == "#continue"
    assert env.elements['input[name="email"]'].value == email
    assert env.elements["#signup-button"].clicks == 1
    # And the trace reads as intent.
    assert any("the signup button" in line for line in trace)
    assert any("the email field" in line for line in trace)


@pytest.mark.asyncio
async def test_the_same_goal_list_runs_against_a_completely_different_world():
    """Nothing in the flow is tied to Reddit's geometry. Move every element and
    resize the viewport; the identical list still achieves it."""
    email = "someone@example.com"
    env = SimulatedEnvironment(
        [SimElement("#signup-button", x=40, y=700, width=300, height=60)],
        width=800,
        height=1200,
    )

    original_up = env.mouse.up

    async def up_then_open(**kwargs):
        await original_up(**kwargs)
        if env.clicked and env.clicked[-1] == "#signup-button" and "#continue" not in env.elements:
            env.elements['[role="dialog"]'] = SimElement(
                '[role="dialog"]', x=20, y=20, width=760, height=600, kind="text"
            )
            env.elements['input[name="email"]'] = SimElement(
                'input[name="email"]', x=60, y=100, width=600, height=70, kind="input"
            )
            env.elements["#continue"] = SimElement("#continue", x=60, y=220, width=600, height=70)

    env.mouse.up = up_then_open  # type: ignore[method-assign]

    await Actor(env=env, profile=derive_for("identity-2")).pursue(reddit_signup_flow(email))

    assert env.clicked[-1] == "#continue"
    assert env.elements['input[name="email"]'].value == email


@pytest.mark.asyncio
async def test_two_identities_running_the_same_flow_behave_differently():
    """Same goals, different people. A fleet where every member moves identically
    has one fingerprint however human each individual looks."""
    async def run(identity: str) -> tuple[float, list]:
        env = fake_reddit()
        await Actor(env=env, profile=derive_for(identity)).pursue(
            reddit_signup_flow("someone@example.com")
        )
        down_points = [(e[1], e[2]) for e in env.events if e[0] == "down"]
        return env.now(), down_points

    first_time, first_points = await run("identity-aaaa")
    second_time, second_points = await run("identity-bbbb")

    assert first_time != second_time, "two personas took exactly the same time"
    assert first_points != second_points, "two personas pressed in exactly the same places"


@pytest.mark.asyncio
async def test_the_flow_contains_no_coordinates_or_timings():
    """A guard on the abstraction itself: the moment a goal list carries a pixel
    or a delay, it has stopped being portable."""
    import dataclasses

    for goal in reddit_signup_flow("someone@example.com"):
        for f in dataclasses.fields(goal):
            value = getattr(goal, f.name)
            if isinstance(value, Target):
                continue
            # count/seconds/timeout are allowed to be None (meaning "ask the
            # profile"); what is not allowed is a hard-coded number.
            assert value is None or isinstance(value, (str, bool)), (
                f"{type(goal).__name__}.{f.name} = {value!r} hard-codes something "
                "the profile or environment should decide"
            )
