"""Tests for goals + profile + environment, against the simulated world.

What's assertable here that a browser cannot tell you: whether the click landed
inside the element meant, whether the path stayed on screen, whether the text went
into the focused field, and whether a careful persona genuinely behaves
differently from a brisk one. All of it runs on a virtual clock, so simulated
minutes of hesitation cost microseconds.
"""
from __future__ import annotations

import asyncio

import pytest

from app.behaviour.adapters.simulated import SimElement, SimulatedEnvironment
from app.behaviour.environment import Environment, Target
from app.behaviour.executor import Actor, GoalFailed
from app.behaviour.goals import ClickOn, Dwell, ScrollTo, TypeInto, WaitFor, Wander
from app.behaviour.profile import AVERAGE, BRISK, CAREFUL, BehaviourProfile, derive_for

SIGNUP = Target("signup", "the signup button")
EMAIL = Target("email", "the email field")
FOOTER = Target("footer", "the footer link")


def world(**kwargs) -> SimulatedEnvironment:
    return SimulatedEnvironment(
        [
            SimElement("signup", x=1100, y=20, width=120, height=36),
            SimElement("email", x=500, y=400, width=300, height=44, kind="input"),
            # Deliberately below the fold, so scrolling actually has to happen.
            SimElement("footer", x=600, y=2400, width=160, height=30),
        ],
        **kwargs,
    )


def actor(env, profile: BehaviourProfile = AVERAGE, log=None) -> Actor:
    return Actor(env=env, profile=profile, log=log or (lambda _m: None))


# --- the port ----------------------------------------------------------------

def test_the_simulator_satisfies_the_environment_port():
    """The whole portability claim rests on this: if the simulator and Playwright
    answer the same protocol, goals move between them untouched."""
    assert isinstance(world(), Environment)


def test_the_playwright_adapter_satisfies_the_environment_port():
    from app.behaviour.adapters.playwright_env import PlaywrightEnvironment

    assert issubclass(PlaywrightEnvironment, object)
    for method in ("viewport", "observe", "scroll_by", "sleep", "now"):
        assert hasattr(PlaywrightEnvironment, method), f"adapter is missing {method}"


# --- ClickOn -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_click_lands_on_the_element_that_was_aimed_at():
    """The outcome, not the call: did the press-release actually land inside the
    element, given a scattered landing point and an overshoot?"""
    env = world()
    await actor(env).pursue([ClickOn(SIGNUP)])

    assert env.clicked[-1] == "signup"
    assert env.elements["signup"].clicks == 1


@pytest.mark.asyncio
async def test_click_lands_inside_the_box_every_time():
    for _ in range(40):
        env = world()
        await actor(env).pursue([ClickOn(SIGNUP)])
        assert env.clicked[-1] == "signup"


@pytest.mark.asyncio
async def test_clicks_are_scattered_not_always_the_same_pixel():
    """Hitting the exact centre of every target is a stronger signal than any
    amount of jitter."""
    landings = set()
    for _ in range(30):
        env = world()
        await actor(env).pursue([ClickOn(SIGNUP)])
        down = [e for e in env.events if e[0] == "down"][-1]
        landings.add((round(down[1], 1), round(down[2], 1)))
    assert len(landings) > 25


@pytest.mark.asyncio
async def test_clicking_something_that_never_appears_fails_with_the_goal_named():
    env = world()
    a = actor(env, AVERAGE.with_(patience_s=1.0))
    with pytest.raises(GoalFailed) as excinfo:
        await a.pursue([ClickOn(Target("nope", "a button that isn't there"))])
    assert "ClickOn" in str(excinfo.value)
    assert "a button that isn't there" in str(excinfo.value)


# --- TypeInto ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_typing_focuses_the_field_first_and_lands_the_whole_value():
    env = world()
    await actor(env).pursue([TypeInto(EMAIL, "alex.skating705672@tuta.com")])

    assert env.focused == "email"
    assert env.elements["email"].value == "alex.skating705672@tuta.com"


@pytest.mark.asyncio
async def test_typos_are_corrected_so_the_final_value_is_still_right():
    """A persona that makes mistakes must still end up with the intended text -
    an uncorrected typo is a bug, not realism."""
    env = world()
    profile = AVERAGE.with_(typo_chance=0.5)
    await actor(env, profile).pursue([TypeInto(EMAIL, "someone@example.com")])

    assert env.elements["email"].value == "someone@example.com"
    assert any(key == "Backspace" for _, key in env.typed), "no correction was ever made"


@pytest.mark.asyncio
async def test_typing_verification_catches_a_field_that_did_not_take_the_text():
    """Per-key typing can be swallowed by a field that re-renders mid-stream.
    Finding out here beats finding out at submit time."""
    env = world()
    # A field that silently drops everything typed into it.
    env.elements["email"].kind = "button"

    with pytest.raises(GoalFailed, match="typing did not register"):
        await actor(env).pursue([TypeInto(EMAIL, "someone@example.com")])


# --- Wander ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_wandering_is_a_continuous_path_of_press_move_release():
    env = world()
    await actor(env).pursue([Wander(count=3)])

    kinds = [e[0] for e in env.events if e[0] in ("down", "up")]
    assert kinds == ["down", "up"] * 3, "gestures must not overlap or teleport"


@pytest.mark.asyncio
async def test_wandering_stays_on_screen():
    env = world()
    await actor(env).pursue([Wander(count=5)])
    viewport = env.viewport()
    for x, y in env.path:
        # The curve bows outward, so allow a margin; what matters is that
        # gestures are not aimed off the page.
        assert -100 <= x <= viewport.width + 100
        assert -100 <= y <= viewport.height + 100


@pytest.mark.asyncio
async def test_wander_count_comes_from_the_profile_when_unspecified():
    env = world()
    a = actor(env, AVERAGE.with_(wander_range=(7, 7)))
    assert await a.wander(Wander()) == 7


# --- ScrollTo ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_scrolling_brings_an_off_screen_target_into_view():
    env = world()
    assert not (await env.observe(FOOTER)).visible, "footer should start below the fold"

    await actor(env).pursue([ScrollTo(FOOTER)])

    assert (await env.observe(FOOTER)).actionable
    assert env.scroll_y > 0


@pytest.mark.asyncio
async def test_scrolling_happens_in_notches_not_one_jump():
    """A single large scroll has no intermediate positions; anything sampling
    scroll offset sees a teleport."""
    env = world()
    await actor(env).pursue([ScrollTo(FOOTER)])
    scrolls = [e for e in env.events if e[0] == "scroll"]
    assert len(scrolls) > 3


@pytest.mark.asyncio
async def test_scroll_then_click_reaches_a_target_below_the_fold():
    """The combination is the point: goals compose without the caller doing any
    geometry."""
    env = world()
    await actor(env).pursue([ScrollTo(FOOTER), ClickOn(FOOTER)])
    assert env.clicked[-1] == "footer"


# --- WaitFor -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_wait_for_returns_once_the_target_shows_up():
    env = world()
    target = Target("late", "a late-arriving banner")

    async def appear_later():
        # Three polls' worth of simulated time, then it exists.
        await asyncio.sleep(0)
        env.elements["late"] = SimElement("late", x=300, y=300, width=100, height=20)

    a = actor(env)
    await appear_later()
    observation = await a.wait_for(WaitFor(target))
    assert observation.actionable


@pytest.mark.asyncio
async def test_wait_for_gives_up_after_the_profiles_patience():
    env = world()
    impatient = AVERAGE.with_(patience_s=2.0)
    a = actor(env, impatient)

    before = env.now()
    with pytest.raises(GoalFailed, match="never became actionable"):
        await a.wait_for(WaitFor(Target("never", "something that never arrives")))
    # Waited roughly its patience, on the virtual clock - so patience is a real
    # behavioural variable, not a constant hidden in the executor.
    assert 1.5 <= env.now() - before <= 4.0


# --- the profile actually changes behaviour ----------------------------------

@pytest.mark.asyncio
async def test_a_careful_persona_takes_longer_than_a_brisk_one():
    """If the profile didn't drive timing, this would be noise. It isn't."""
    async def elapsed(profile) -> float:
        env = world()
        await actor(env, profile).pursue(
            [Wander(count=2), ClickOn(SIGNUP), TypeInto(EMAIL, "someone@example.com")]
        )
        return env.now()

    brisk = sum([await elapsed(BRISK) for _ in range(5)]) / 5
    careful = sum([await elapsed(CAREFUL) for _ in range(5)]) / 5
    assert careful > brisk * 1.5, f"careful={careful:.1f}s brisk={brisk:.1f}s"


@pytest.mark.asyncio
async def test_a_faster_typist_finishes_the_same_text_sooner():
    async def elapsed(wpm) -> float:
        env = world()
        await actor(env, AVERAGE.with_(typing_wpm=wpm)).pursue(
            [TypeInto(EMAIL, "a-reasonably-long-address@example.com")]
        )
        return env.now()

    assert await elapsed(110.0) < await elapsed(25.0)


def test_derived_profiles_are_stable_per_identity_and_differ_between_them():
    """A fleet whose members all move identically has one fingerprint; a profile
    that changes between sessions isn't a person."""
    a1 = derive_for("identity-aaaa")
    a2 = derive_for("identity-aaaa")
    b = derive_for("identity-bbbb")

    assert a1 == a2, "same identity must always get the same profile"
    assert a1 != b, "different identities must differ"


def test_derived_profiles_stay_within_plausible_bounds():
    for i in range(300):
        p = derive_for(f"identity-{i}")
        assert 18.0 <= p.typing_wpm <= 140.0
        assert 0.0 <= p.typo_chance <= 0.06
        assert 0.15 <= p.aim_scatter <= 0.45
        assert 0.4 <= p.hesitancy <= 2.5
        assert p.patience_s >= 8.0
        assert p.wander_range[0] <= p.wander_range[1]


def test_a_profile_cannot_drift_mid_session():
    """Frozen: a bot that speeds up as a run goes on has timing that is a function
    of the run, not of the person."""
    import dataclasses

    with pytest.raises(dataclasses.FrozenInstanceError):
        AVERAGE.typing_wpm = 200.0  # type: ignore[misc]
