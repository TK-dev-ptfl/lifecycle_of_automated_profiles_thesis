from unittest.mock import patch

import pytest
from playwright.async_api import async_playwright

from app.pipelines.email_pool.providers import tuta
from app.pipelines.email_pool.providers.tuta import (
    IP_BLOCKED_TEXT,
    TutaSignupContext,
    _raise_if_ip_blocked,
    step_accept_agreements,
    step_check_recovery_kit_box,
    step_manual_captcha,
)


@pytest.mark.asyncio
async def test_captcha_step_always_waits_for_manual_confirmation():
    """For now step_manual_captcha always waits for a human, even when the
    recovery-kit checkbox is already visible (which used to trigger an
    auto-skip) - that auto-skip was racing ahead of CAPTCHAs that were still
    loading, so every run now stops here until a person confirms."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<input type="checkbox">')
            wait_called = False

            async def fake_wait(prompt: str) -> None:
                nonlocal wait_called
                wait_called = True

            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)
            await step_manual_captcha(ctx)

            assert wait_called is True
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_captcha_step_waits_then_verifies_recovery_checkbox_appeared():
    """No checkbox yet when the step starts - it must still wait for manual
    confirmation, then verify (not just trust) that the recovery-kit
    checkbox actually appeared afterward. Here fake_wait simulates a
    correctly-solved CAPTCHA by adding the checkbox once "confirmed", so the
    post-check should pass."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<div>captcha challenge placeholder, no checkbox here</div>')
            wait_called = False

            async def fake_wait(prompt: str) -> None:
                nonlocal wait_called
                wait_called = True
                # Simulate the CAPTCHA actually being solved: the recovery-kit
                # page (with its checkbox) now appears.
                await page.set_content('<input type="checkbox">')

            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)
            await step_manual_captcha(ctx)

            assert wait_called is True
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_captcha_step_raises_when_confirmed_but_recovery_checkbox_never_appears():
    """If the operator says "done" but the recovery-kit page never actually
    shows up (CAPTCHA not really solved, page stuck, etc), this must not
    silently continue as if it worked - it should raise."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<div>captcha challenge placeholder, no checkbox here</div>')

            async def fake_wait(prompt: str) -> None:
                pass  # confirms "done" but never adds the checkbox - nothing changes

            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page, wait_for_manual=fake_wait)

            with patch.object(tuta, "VERIFY_TIMEOUT_MS", 500), \
                 pytest.raises(RuntimeError, match="recovery-kit page never appeared"):
                await step_manual_captcha(ctx)
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_check_recovery_kit_box_raises_if_click_does_not_actually_check_it():
    """Regression test for the exact bug reported live: the pipeline moved
    on to the next step even though the recovery-kit checkbox was never
    actually checked. A page whose checkbox resets itself on click (via
    onclick) simulates a click that doesn't register as intended - Playwright
    happily clicks it (it's a normal enabled element), but is_checked() comes
    back False afterward, which must raise rather than be ignored."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()
        try:
            await page.set_content('<input type="checkbox" onclick="this.checked=false">')
            ctx = TutaSignupContext(username="x", password="y", context=page.context, page=page)

            with pytest.raises(RuntimeError, match="did not become checked"):
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
