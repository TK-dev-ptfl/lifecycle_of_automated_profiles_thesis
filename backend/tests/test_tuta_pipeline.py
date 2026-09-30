import asyncio
from unittest.mock import patch

import pytest
from playwright.async_api import async_playwright

from app.pipelines.email_pool.providers import tuta
from app.pipelines.email_pool.providers.tuta import (
    IP_BLOCKED_TEXT,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    TutaSignupContext,
    _raise_if_ip_blocked,
    generate_username,
    generate_username_from_identity,
    step_accept_agreements,
    step_captcha_sleep,
    step_check_recovery_kit_box,
)

# --- Generated address length -------------------------------------------------
#
# Tuta refuses an address that already exists, and short name-shaped local parts
# ("alexsmith", "jordan42") are long since taken on a mail host that old - being
# rejected as unavailable was the main way step_fill_credentials used to burn
# through all MAX_USERNAME_ATTEMPTS.

NAME_SAMPLES = [
    ("Alex Smith", 28),
    ("Jordan Miller", 34),
    ("Zuzana Kováčová", 41),   # diacritics must be stripped, not dropped whole
    ("Li Wei", None),           # no age: the tail comes from a plain number
    ("Mária", 25),              # single name, no surname to build on
    ("!!!", 33),                # nothing usable at all -> falls back
]


@pytest.mark.parametrize("display_name,age", NAME_SAMPLES)
def test_generated_addresses_are_always_long_enough_to_be_free(display_name, age):
    for _ in range(200):
        username = generate_username_from_identity(display_name, age)
        assert USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH, username


def test_no_name_fallback_is_also_long_and_not_obviously_generated():
    for _ in range(200):
        username = generate_username()
        assert USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH, username
        # The old fallback was "bot" + hex, which is both short enough to
        # collide and exactly the signal thesis 2.2.3 flags.
        assert not username.startswith("bot")


@pytest.mark.parametrize("display_name,age", NAME_SAMPLES)
def test_generated_addresses_are_valid_local_parts(display_name, age):
    """Only characters Tuta's username field accepts, and no leading/trailing
    separator - "alexsmith." would be rejected outright, which is the one
    rejection retrying cannot fix."""
    for _ in range(200):
        username = generate_username_from_identity(display_name, age)
        assert all(c.isalnum() or c in "._" for c in username), username
        assert not username.startswith((".", "_")) and not username.endswith((".", "_")), username
        assert username == username.lower(), username


def test_generated_addresses_always_carry_a_numeric_tail():
    """The old generator had a branch that appended no number at all, which
    produced precisely the plain, already-taken addresses this is meant to
    avoid. The tail is also where most of the entropy lives, so it must never be
    the part that gets trimmed to fit the length cap."""
    for _ in range(300):
        username = generate_username_from_identity("Alex Smith", 28)
        assert username[-1].isdigit(), username


def test_generated_addresses_do_not_repeat_for_one_identity():
    """Two identities can share a display name and age; their addresses must
    still differ, or the second run fails on an address the first one took."""
    generated = {generate_username_from_identity("Alex Smith", 28) for _ in range(2000)}
    # Comfortably unique - a handful of repeats in 2000 draws from one single
    # name would still be fine (step_fill_credentials retries on rejection), but
    # anything near the old generator's rate would not.
    assert len(generated) > 1950, f"only {len(generated)} distinct addresses in 2000 draws"

# step_manual_captcha is disabled for now (see tuta.py - swapped out for
# step_captcha_sleep in PIPELINE_STEPS), so it's no longer importable. The
# three tests below cover its behavior and are commented out alongside it;
# re-enable both together.
#
# from app.pipelines.email_pool.providers.tuta import step_manual_captcha
#
#
# @pytest.mark.asyncio
# async def test_captcha_step_always_waits_for_manual_confirmation():
#     """For now step_manual_captcha always waits for a human, even when the
#     recovery-kit checkbox is already visible (which used to trigger an
#     auto-skip) - that auto-skip was racing ahead of CAPTCHAs that were still
#     loading, so every run now stops here until a person confirms."""
#     async with async_playwright() as pw:
#         browser = await pw.chromium.launch(headless=True)
#         page = await (await browser.new_context()).new_page()
#         try:
#             await page.set_content('<input type="checkbox">')
#             wait_called = False
#
#             async def fake_wait(prompt: str) -> None:
#                 nonlocal wait_called
#                 wait_called = True
#
#             ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)
#             await step_manual_captcha(ctx)
#
#             assert wait_called is True
#         finally:
#             await browser.close()
#
#
# @pytest.mark.asyncio
# async def test_captcha_step_waits_then_verifies_recovery_checkbox_appeared():
#     """No checkbox yet when the step starts - it must still wait for manual
#     confirmation, then verify (not just trust) that the recovery-kit
#     checkbox actually appeared afterward. Here fake_wait simulates a
#     correctly-solved CAPTCHA by adding the checkbox once "confirmed", so the
#     post-check should pass."""
#     async with async_playwright() as pw:
#         browser = await pw.chromium.launch(headless=True)
#         page = await (await browser.new_context()).new_page()
#         try:
#             await page.set_content('<div>captcha challenge placeholder, no checkbox here</div>')
#             wait_called = False
#
#             async def fake_wait(prompt: str) -> None:
#                 nonlocal wait_called
#                 wait_called = True
#                 # Simulate the CAPTCHA actually being solved: the recovery-kit
#                 # page (with its checkbox) now appears.
#                 await page.set_content('<input type="checkbox">')
#
#             ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)
#             await step_manual_captcha(ctx)
#
#             assert wait_called is True
#         finally:
#             await browser.close()
#
#
# @pytest.mark.asyncio
# async def test_captcha_step_raises_when_confirmed_but_recovery_checkbox_never_appears():
#     """If the operator says "done" but the recovery-kit page never actually
#     shows up (CAPTCHA not really solved, page stuck, etc), this must not
#     silently continue as if it worked - it should raise."""
#     async with async_playwright() as pw:
#         browser = await pw.chromium.launch(headless=True)
#         page = await (await browser.new_context()).new_page()
#         try:
#             await page.set_content('<div>captcha challenge placeholder, no checkbox here</div>')
#
#             async def fake_wait(prompt: str) -> None:
#                 pass  # confirms "done" but never adds the checkbox - nothing changes
#
#             ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)
#
#             with patch.object(tuta, "VERIFY_TIMEOUT_MS", 500), \
#                  pytest.raises(RuntimeError, match="recovery-kit page never appeared"):
#                 await step_manual_captcha(ctx)
#         finally:
#             await browser.close()


@pytest.mark.asyncio
async def test_check_recovery_kit_box_raises_if_click_does_not_actually_check_it():
    """Regression test for the exact bug reported live: the pipeline moved
    on to the next step even though the recovery-kit checkbox was never
    actually checked. A page whose checkbox resets itself on click (via
    onclick) simulates a click that doesn't register as intended - Playwright
    happily clicks it (it's a normal enabled element), but is_checked() comes
    back False afterward, which must raise rather than be ignored. Includes
    the recovery-kit page's own Continue button so the step's own
    page-identity check (added after a *different* bug - see the
    test_captcha_sleep_step tests below) passes and this test actually
    reaches the checkbox-click assertion it's testing."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content(
                '<button data-testid="btn:recovery_kit_page_continue_label">Continue</button>'
                '<input type="checkbox" onclick="this.checked=false">'
            )
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with pytest.raises(RuntimeError, match="did not become checked"):
                await step_check_recovery_kit_box(ctx)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_check_recovery_kit_box_refuses_to_click_on_the_wrong_page():
    """Regression test for the bug reported live: a checkbox belonging to a
    different page (a CAPTCHA challenge's own "I'm not a robot" widget, or
    the agreements page a few steps earlier) could satisfy a bare
    "input[type=checkbox]" selector even though the pipeline never actually
    reached the recovery-kit page. Without the recovery-kit page's own
    Continue button present, this must refuse to click anything at all."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            # A checkbox is present - just not on the recovery-kit page.
            await page.set_content('<div>some other page</div><input type="checkbox">')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with patch.object(tuta, "VERIFY_TIMEOUT_MS", 500), \
                 pytest.raises(RuntimeError, match="recovery-kit page isn't actually showing"):
                await step_check_recovery_kit_box(ctx)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_accept_agreements_raises_if_a_checkbox_does_not_actually_check():
    """Same regression as above, for the agreements step - only the second
    checkbox fails to register, and it must still be caught even though the
    first one worked fine."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content(
                '<div class="flex col gap-4 smaller justify-start mt-16">'
                '<input type="checkbox">'
                '<input type="checkbox" onclick="this.checked=false">'
                "</div>"
            )
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with pytest.raises(RuntimeError, match="checkbox 1 did not become checked"):
                await step_accept_agreements(ctx)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_raise_if_ip_blocked_detects_tuta_abuse_banner():
    """Tuta shows this exact banner when it's blocked the signup IP for
    suspected abuse - very commonly the proxy, especially the free/public
    sources this pool draws from. There's nothing to retry or wait out, so
    this must raise immediately and by name, not let the pipeline barrel on
    into steps that assume a normal page state."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content(f'<div class="text-break selectable">{IP_BLOCKED_TEXT}</div>')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with pytest.raises(RuntimeError, match="Tuta blocked this IP"):
                await _raise_if_ip_blocked(ctx)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_raise_if_ip_blocked_does_nothing_when_banner_absent():
    """A normal page (no abuse banner) must not trip this check."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<div>Vitejte v Tuta</div>')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            await _raise_if_ip_blocked(ctx)  # must not raise
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_captcha_sleep_step_waits_for_recovery_page_anchor_to_appear():
    """step_manual_captcha's replacement must not just sleep-then-continue -
    it needs to actually wait for the recovery-kit page itself to show up,
    exactly like the disabled step used to verify after a human confirmed.
    Anchored on the page's own Continue button rather than a bare checkbox -
    a CAPTCHA challenge commonly renders its own checkbox widget, which would
    otherwise satisfy a plain checkbox wait without the real recovery-kit
    page ever having loaded (the exact bug reported live). Simulates the
    real page appearing partway through the wait."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            # A checkbox is already present - e.g. a CAPTCHA widget's own -
            # but NOT the recovery-kit page's Continue button. This must not
            # be satisfied by that checkbox alone.
            await page.set_content('<div>captcha challenge</div><input type="checkbox">')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            async def add_recovery_page_shortly():
                await asyncio.sleep(0.3)
                await page.set_content(
                    '<button data-testid="btn:recovery_kit_page_continue_label">Continue</button>'
                    '<input type="checkbox">'
                )

            task = asyncio.create_task(add_recovery_page_shortly())
            try:
                await step_captcha_sleep(ctx)
            finally:
                await task
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_captcha_sleep_step_raises_if_recovery_page_never_appears():
    """If the page never gets to the recovery-kit page (e.g. a real CAPTCHA
    is blocking with no human to solve it, since step_manual_captcha is
    currently disabled), this must raise rather than silently continuing
    into step_check_recovery_kit_box against a page that was never reached.
    A checkbox is present (as a CAPTCHA widget's might be) but the
    recovery-kit page's own Continue button never appears."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<div>stuck on a captcha</div><input type="checkbox">')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with patch.object(tuta, "CAPTCHA_AUTO_WAIT_TIMEOUT_MS", 500), \
                 pytest.raises(RuntimeError, match="recovery-kit page never appeared"):
                await step_captcha_sleep(ctx)
        finally:
            await browser.close()
