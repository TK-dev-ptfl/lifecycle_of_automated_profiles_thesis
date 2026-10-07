"""Tests for the Reddit signup steps.

Driven against fake locators rather than a browser: what these pin down is the
decision logic - when the humanity step blocks and when it skips, which selector
fallbacks are tried, that a step verifies its own outcome instead of assuming it.
Whether the selectors match today's Reddit is something only a live run can say,
and no unit test can.
"""
from __future__ import annotations

import asyncio

import pytest

from app.pipelines.reddit import describe_pipeline, selectors
from app.pipelines.reddit.context import RedditSignupContext
from app.pipelines.reddit.steps.approach_signup import step_approach_signup
from app.pipelines.reddit.steps.enter_email import step_enter_email
from app.pipelines.reddit.steps.humanity_check import step_humanity_check
from app.pipelines.reddit.steps.submit_email import step_submit_email

EMAIL = "alexsmith.skating705672@tuta.com"
BOX = {"x": 400.0, "y": 300.0, "width": 160.0, "height": 44.0}


# --- fakes -------------------------------------------------------------------

class FakeLocator:
    def __init__(self, *, visible=True, box=BOX, text="", value="", count=1, attrs=None):
        self._visible = visible
        self._box = box
        self._text = text
        self._value = value
        self._count = count
        self._attrs = attrs or {}

    @property
    def first(self):
        return self

    async def wait_for(self, *, state="visible", timeout=None):
        if not self._visible:
            raise TimeoutError("not visible")

    async def bounding_box(self):
        return self._box

    async def count(self):
        return self._count

    async def is_visible(self):
        return self._visible

    async def inner_text(self):
        return self._text

    async def input_value(self):
        return self._value

    async def get_attribute(self, name):
        return self._attrs.get(name)


class FakePage:
    """Resolves locators from a {selector: FakeLocator} map; anything unmapped is
    reported as absent, which is how the fallback chains get exercised."""

    def __init__(self, mapping=None, viewport=None):
        self.mapping = mapping or {}
        self._viewport = viewport or {"width": 1366, "height": 900}
        self.mouse = _NullMouse()
        self.keyboard = _NullKeyboard()
        self.asked: list[str] = []

    @property
    def viewport_size(self):
        return dict(self._viewport)

    def locator(self, selector, **kwargs):
        self.asked.append(selector)
        # has_text is used by the humanity check; the map keys encode it.
        if "has_text" in kwargs:
            selector = f"{selector}|{kwargs['has_text']}"
        return self.mapping.get(selector, FakeLocator(visible=False, count=0))

    async def evaluate(self, expression, arg=None):
        return None


class _NullMouse:
    async def move(self, x, y, *, steps=1): pass
    async def down(self, **kw): pass
    async def up(self, **kw): pass


class _NullKeyboard:
    async def press(self, key, *, delay=None): pass
    async def type(self, text, *, delay=None): pass


def _ctx(page, *, email=EMAIL, gate=None):
    from app.behaviour.algorithms.cursor import Cursor

    ctx = RedditSignupContext(email=email, context=None, page=page)
    ctx.cursor = Cursor(page, at=(60.0, 60.0))
    if gate is not None:
        ctx.wait_for_manual = gate
    return ctx


@pytest.fixture(autouse=True)
def _no_real_pauses(monkeypatch):
    """The steps call the behaviour layer, which sleeps for human-plausible
    stretches. Collapse those so the suite stays fast."""
    async def instant(seconds):
        return None

    for module in (
        "app.behaviour.primitives.timing",
        "app.behaviour.primitives.mouse",
        "app.behaviour.primitives.keyboard",
        "app.behaviour.algorithms.cursor",
        "app.behaviour.algorithms.forms",
        "app.pipelines.reddit.steps.open_homepage",
        "app.pipelines.reddit.steps.submit_email",
    ):
        try:
            monkeypatch.setattr(f"{module}._real_sleep", instant, raising=False)
        except Exception:
            pass
    monkeypatch.setattr("asyncio.sleep", instant)


# --- the step list -----------------------------------------------------------

def test_pipeline_order_and_manual_steps():
    steps = describe_pipeline()
    assert [s["name"] for s in steps] == [
        "open_homepage",
        "humanity_check",
        "approach_signup",
        "await_signup_dialog",
        "enter_email",
        "submit_email",
        "await_email_verification",
    ]
    # Both of these can block for a person, and the dashboard needs to know that
    # in advance to offer a Continue button.
    assert {s["name"] for s in steps if s["manual"]} == {
        "humanity_check",
        "await_email_verification",
    }


# --- humanity check ----------------------------------------------------------

@pytest.mark.asyncio
async def test_humanity_check_skips_when_the_challenge_is_absent():
    """Reddit shows this on some IPs and not others, so absence is the common
    case and must not block or fail."""
    waited = []
    page = FakePage()  # nothing mapped -> heading not found
    ctx = _ctx(page, gate=lambda prompt: waited.append(prompt))

    await step_humanity_check(ctx)

    assert waited == [], "must not wait for a human when there is no challenge"
    assert ctx.humanity_challenge_shown is False
    assert any("No humanity challenge" in line for line in ctx.log)


@pytest.mark.asyncio
async def test_humanity_check_waits_for_a_human_when_the_challenge_is_shown():
    key = f"{selectors.HUMANITY_HEADING_SELECTOR}|{selectors.HUMANITY_HEADING}"
    seen = {"calls": 0}

    class Heading(FakeLocator):
        async def wait_for(self, *, state="visible", timeout=None):
            # Present on the first look, gone after the human has solved it.
            seen["calls"] += 1
            if seen["calls"] > 1:
                raise TimeoutError("cleared")

    prompts = []

    async def gate(prompt):
        prompts.append(prompt)

    ctx = _ctx(FakePage({key: Heading()}), gate=gate)
    await step_humanity_check(ctx)

    assert len(prompts) == 1
    assert selectors.HUMANITY_HEADING in prompts[0]
    assert ctx.humanity_challenge_shown is True
    assert any("cleared" in line for line in ctx.log)


@pytest.mark.asyncio
async def test_humanity_check_warns_if_still_present_after_confirmation():
    """Someone can press Continue early. Saying so now beats a confusing failure
    three steps later when the signup button turns out not to exist."""
    key = f"{selectors.HUMANITY_HEADING_SELECTOR}|{selectors.HUMANITY_HEADING}"

    async def gate(prompt):
        return None

    ctx = _ctx(FakePage({key: FakeLocator()}), gate=gate)
    await step_humanity_check(ctx)

    assert any("still on screen" in line for line in ctx.log)


# --- approach signup ---------------------------------------------------------

@pytest.mark.asyncio
async def test_approach_signup_drags_then_clicks_the_button_by_id():
    page = FakePage({selectors.SIGNUP_BUTTON: FakeLocator()})
    ctx = _ctx(page)

    await step_approach_signup(ctx)

    assert any("idle mouse drag" in line for line in ctx.log)
    assert any(selectors.SIGNUP_BUTTON in line for line in ctx.log)
    assert any("Clicked the signup button" in line for line in ctx.log)


@pytest.mark.asyncio
async def test_approach_signup_falls_back_to_the_register_link():
    """Reddit renaming an id must not take the run down when the link is still
    there pointing at the register route."""
    page = FakePage({selectors.SIGNUP_LINK_FALLBACK: FakeLocator()})
    ctx = _ctx(page)

    await step_approach_signup(ctx)
    assert any(selectors.SIGNUP_LINK_FALLBACK in line for line in ctx.log)


@pytest.mark.asyncio
async def test_approach_signup_fails_clearly_when_no_button_exists():
    ctx = _ctx(FakePage())
    with pytest.raises(RuntimeError, match="approach_signup"):
        await step_approach_signup(ctx)


@pytest.mark.asyncio
async def test_approach_signup_refuses_a_button_with_no_bounding_box():
    """Visible in the accessibility tree but not laid out: clicking by coordinate
    would hit whatever is underneath it."""
    page = FakePage({selectors.SIGNUP_BUTTON: FakeLocator(box=None)})
    with pytest.raises(RuntimeError, match="no bounding box"):
        await step_approach_signup(_ctx(page))


# --- enter email -------------------------------------------------------------

@pytest.mark.asyncio
async def test_enter_email_types_the_identitys_address_and_verifies_it():
    key = f"{selectors.SIGNUP_DIALOG} {selectors.EMAIL_FIELD_CANDIDATES[0]}"
    page = FakePage({key: FakeLocator(value=EMAIL)})
    ctx = _ctx(page)

    await step_enter_email(ctx)

    assert page.keyboard is not None
    assert any(f"verified as {EMAIL}" in line for line in ctx.log)


@pytest.mark.asyncio
async def test_enter_email_fails_when_the_field_did_not_take_the_text():
    """Per-key typing can be swallowed by a field that re-rendered mid-stream;
    better to find out here than to submit a half-typed address."""
    key = f"{selectors.SIGNUP_DIALOG} {selectors.EMAIL_FIELD_CANDIDATES[0]}"
    page = FakePage({key: FakeLocator(value="alexsm")})
    with pytest.raises(RuntimeError, match="typing did not register"):
        await step_enter_email(_ctx(page))


@pytest.mark.asyncio
async def test_enter_email_refuses_an_identity_with_no_mailbox():
    """The whole point of the run is to register the address the email pipeline
    produced, so there is nothing to fall back to."""
    with pytest.raises(RuntimeError, match="no email address"):
        await step_enter_email(_ctx(FakePage(), email=""))


# --- submit email ------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_email_clicks_continue_and_accepts_a_silent_form():
    key = selectors.CONTINUE_BUTTON_CANDIDATES[0]
    page = FakePage({key: FakeLocator()})
    ctx = _ctx(page)

    await step_submit_email(ctx)
    assert any("Email accepted" in line for line in ctx.log)


@pytest.mark.asyncio
async def test_submit_email_fails_on_an_inline_rejection():
    """An address Reddit will not take never produces a verification mail, so
    every later step would wait for something that is not coming."""
    page = FakePage({
        selectors.CONTINUE_BUTTON_CANDIDATES[0]: FakeLocator(),
        selectors.EMAIL_ERROR_CANDIDATES[0]: FakeLocator(text="Email already in use"),
    })
    with pytest.raises(RuntimeError, match="already in use"):
        await step_submit_email(_ctx(page))
