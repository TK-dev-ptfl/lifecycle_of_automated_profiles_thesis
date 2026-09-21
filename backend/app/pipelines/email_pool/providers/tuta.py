"""Automated Tuta Mail (tuta.com) signup pipeline.

Mirrors thesis chapter 3.5.1's Creation pipeline design: the signup flow is
broken into small, independently named/loggable steps rather than one long
function. Tuta's signup requires solving an interactive CAPTCHA, which can't
be automated here, so the pipeline runs a headful (visible) browser and
pauses on that one step until a human confirms it's done.

Run directly to try it end-to-end:

    cd backend
    .venv\\Scripts\\python -m app.pipelines.email_pool.providers.tuta

Selectors are pinned to tuta.com's current DOM (data-testid where available,
element id/class otherwise) as of this writing. If Tuta changes their
frontend, the steps that broke will raise a Playwright TimeoutError naming
the selector — update that one step, the rest of the pipeline is unaffected.
"""
from __future__ import annotations

import asyncio
import random
import re
import secrets
import string
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Optional, TypedDict

from playwright.async_api import BrowserContext, Page, async_playwright

TUTA_HOME_URL = "https://tuta.com/cs"

# Pause between automatic steps, seconds. Firing every action the instant the
# previous one finishes is itself a bot signal (see thesis 2.2.1 - behavioral
# detectors flag near-zero, uniform inter-action timing); this keeps pacing
# irregular and roughly human instead.
STEP_DELAY_RANGE = (1.4, 3.8)
# Per-keystroke delay, milliseconds, for the two fields human-speed matters
# most on (username/password) rather than Playwright's instant .fill().
TYPE_DELAY_RANGE_MS = (60, 150)


async def _human_delay(min_s: float = STEP_DELAY_RANGE[0], max_s: float = STEP_DELAY_RANGE[1]) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def _typing_delay() -> float:
    return random.uniform(*TYPE_DELAY_RANGE_MS)


def generate_username(prefix: str = "bot") -> str:
    """Fallback used only when there's no identity name to base a username
    on (e.g. running this file standalone). An obviously-automated
    "bot3c4e660b"-style address is otherwise exactly the kind of signal
    thesis 2.2.3 flags - real accounts don't look like that."""
    return f"{prefix}{secrets.token_hex(4)}"


def _name_parts(display_name: str) -> list[str]:
    ascii_only = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii")
    return [p for p in (re.sub(r"[^a-z0-9]", "", w.lower()) for w in ascii_only.split()) if p]


def generate_username_from_identity(display_name: str, age: Optional[int] = None) -> str:
    """Real people don't all pick 'name + 3 random digits' - some use their
    birth year, some just initials, some no number at all. Picks one of
    several realistic patterns each time instead of always the same shape,
    so a whole fleet of these doesn't look like a template was run through a
    counter. Falls back to generate_username() if the name yields nothing
    usable (empty/symbols-only)."""
    parts = _name_parts(display_name)
    if not parts:
        return generate_username()

    first = parts[0]
    last = parts[1] if len(parts) > 1 else ""
    sep = random.choice(["", "", "", ".", "_"])  # no separator is the common case

    if last:
        pattern = random.choice([
            "first_last", "last_first", "first_initial_last", "first_last_initial", "first_only",
        ])
    else:
        pattern = "first_only"

    if pattern == "first_last":
        core = f"{first}{sep}{last}"
    elif pattern == "last_first":
        core = f"{last}{sep}{first}"
    elif pattern == "first_initial_last":
        core = f"{first[0]}{sep}{last}"
    elif pattern == "first_last_initial":
        core = f"{first}{sep}{last[0]}"
    else:
        core = first

    # Numeric suffix: a birth year (full or 2-digit) derived from the
    # identity's actual age when we have one, a small random number, or
    # nothing at all - varying which, instead of a uniform 3-digit code
    # every time, is what actually reads as human.
    suffix = ""
    roll = random.random()
    if age is not None and roll < 0.45:
        birth_year = date.today().year - age - random.randint(0, 1)
        suffix = str(birth_year) if random.random() < 0.5 else f"{birth_year % 100:02d}"
    elif roll < 0.75:
        suffix = str(random.randint(1, 999))
    # else: no numeric suffix at all

    username = re.sub(r"[^a-z0-9._]", "", f"{core}{suffix}".lower()).strip("._")
    return username[:20] or generate_username()


def generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class ProxyConfig(TypedDict, total=False):
    server: str
    username: str
    password: str


async def _apply_stealth(page: Page) -> None:
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        return
    await stealth_async(page)


async def _wait_via_stdin(prompt: str) -> None:
    """Default manual-step waiter for running this file directly as a script
    (python -m app...tuta) - blocks on the *calling process's* own terminal.

    Not used when run through the dashboard: a backgrounded/nohup'd uvicorn
    process typically has no attached interactive stdin, so input() raises
    EOFError immediately instead of blocking - which used to abort the whole
    pipeline (and close the browser) right at the CAPTCHA step. See
    identity_service.start_email_pipeline_for_identity for the real waiter
    used there, gated on a dashboard button instead of stdin."""
    await asyncio.to_thread(input, prompt)


@dataclass
class TutaSignupContext:
    username: str
    password: str
    context: BrowserContext
    page: Optional[Page] = None
    log: list[str] = field(default_factory=list)
    wait_for_manual: Callable[[str], Awaitable[None]] = _wait_via_stdin
    # Kept so step_fill_credentials can generate a fresh candidate in the same
    # style if Tuta rejects the first one as an invalid address.
    display_name: Optional[str] = None
    age: Optional[int] = None

    def record(self, message: str) -> None:
        self.log.append(message)
        print(f"[tuta-signup] {message}")

    def next_username_candidate(self) -> str:
        if self.display_name:
            return generate_username_from_identity(self.display_name, self.age)
        return generate_username()


# --- Individual pipeline steps ------------------------------------------------
# Each step takes the shared context, performs one action, and returns nothing
# (it mutates ctx.page / ctx.log). Keeping them as separate functions is what
# lets each one be logged, retried, or swapped out independently later.

async def step_open_homepage(ctx: TutaSignupContext) -> None:
    page = await ctx.context.new_page()
    await _apply_stealth(page)
    await page.goto(TUTA_HOME_URL, wait_until="domcontentloaded")
    ctx.page = page
    ctx.record(f"Opened {TUTA_HOME_URL}")


async def step_click_signup(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    # tuta.com renders #signup-button twice (desktop header + hidden mobile
    # nav); ":visible" picks whichever copy is actually on screen instead of
    # always matching the first (possibly hidden) one in DOM order.
    # The Registrace link opens app.tuta.com in a new tab (target="_blank").
    async with ctx.context.expect_page() as new_page_info:
        await ctx.page.click("#signup-button:visible")
    signup_page = await new_page_info.value
    await _apply_stealth(signup_page)
    await signup_page.wait_for_load_state("domcontentloaded")
    ctx.page = signup_page
    ctx.record("Clicked Registrace, switched to signup tab")


async def step_select_free_plan(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    free_option = ctx.page.locator("div.flex-space-between.items-center.pb-16").filter(has_text="Free")
    await free_option.locator("input[type=radio]").click()
    ctx.record("Selected Free plan")


async def step_continue_after_plan(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    await ctx.page.click('[data-testid="btn:continue_action"]')
    ctx.record("Clicked Pokracovat after plan selection")


INVALID_EMAIL_ERROR_TEXT = "E-mailová adresa není platná."
MAX_USERNAME_ATTEMPTS = 5


async def _username_rejected_as_invalid(page: Page) -> bool:
    # Matched on the exact error text rather than the "mt-8" class alone -
    # that class is just a generic Tailwind-style margin utility and could
    # easily be reused elsewhere on the page for unrelated reasons.
    return await page.get_by_text(INVALID_EMAIL_ERROR_TEXT, exact=True).count() > 0


async def step_fill_credentials(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    page = ctx.page
    username_field = page.locator('[data-testid="tfi:username_label"]')

    # press_sequentially types one key at a time with a per-keystroke delay,
    # instead of .fill()'s instant paste-in - closer to how a person actually
    # types a username/password.
    for attempt in range(1, MAX_USERNAME_ATTEMPTS + 1):
        await username_field.press_sequentially(ctx.username, delay=_typing_delay())
        # Tuta's inline validation renders near-instantly on blur/input, but
        # give it a beat before checking - this also doubles as the usual
        # human-like pause before moving to the next field.
        await _human_delay(0.4, 1.0)
        if not await _username_rejected_as_invalid(page):
            break
        ctx.record(f"Username '{ctx.username}' rejected as invalid (attempt {attempt}/{MAX_USERNAME_ATTEMPTS})")
        if attempt == MAX_USERNAME_ATTEMPTS:
            ctx.record(f"Still rejected after {MAX_USERNAME_ATTEMPTS} attempts, proceeding with '{ctx.username}' anyway")
            break
        await username_field.fill("")
        ctx.username = ctx.next_username_candidate()

    await page.locator('[data-testid="tfi:newPassword_label"]').press_sequentially(
        ctx.password, delay=_typing_delay()
    )
    await _human_delay(0.4, 1.2)
    await page.locator('[data-testid="tfi:repeatedPassword_label"]').press_sequentially(
        ctx.password, delay=_typing_delay()
    )
    ctx.record(f"Filled username '{ctx.username}' and password")


async def step_accept_agreements(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    checkboxes = ctx.page.locator("div.flex.col.gap-4.smaller.justify-start.mt-16 input[type=checkbox]")
    count = await checkboxes.count()
    for i in range(count):
        if i > 0:
            await _human_delay(0.5, 1.4)
        await checkboxes.nth(i).click()
    ctx.record(f"Checked {count} agreement checkbox(es)")


async def step_submit_account(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    await ctx.page.click('[data-testid="btn:create_new_account_label"]')
    ctx.record("Submitted account creation form (Vytvorit ucet)")


async def step_manual_captcha(ctx: TutaSignupContext) -> None:
    """Tuta shows an interactive CAPTCHA at this point. The browser window is
    visible (headful) — solve it by hand, then confirm via ctx.wait_for_manual
    (stdin prompt for the standalone script, a dashboard button click when
    run through identity_service). Either way this just awaits a signal - the
    browser itself is untouched and stays open exactly as it is for however
    long that takes."""
    ctx.record("Waiting for manual CAPTCHA completion in the browser window...")
    await ctx.wait_for_manual(
        "Solve the CAPTCHA in the browser window, then press Enter here to continue... "
    )
    ctx.record("Manual CAPTCHA step confirmed done by operator")


async def step_check_recovery_kit_box(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    await ctx.page.locator("input[type=checkbox]").first.click()
    ctx.record("Checked recovery kit acknowledgement box")


async def step_finish_recovery_kit(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    await ctx.page.click('[data-testid="btn:recovery_kit_page_continue_label"]')
    ctx.record("Clicked Pojdme zacit - signup complete")


@dataclass
class PipelineStep:
    """One named step of the pipeline. manual=False steps run immediately
    back-to-back with no pause; manual=True steps block for human input
    (currently only the CAPTCHA) before the next automatic step continues."""

    name: str
    fn: Callable[[TutaSignupContext], Awaitable[None]]
    manual: bool = False


PIPELINE_STEPS: list[PipelineStep] = [
    PipelineStep("open_homepage", step_open_homepage),
    PipelineStep("click_signup", step_click_signup),
    PipelineStep("select_free_plan", step_select_free_plan),
    PipelineStep("continue_after_plan", step_continue_after_plan),
    PipelineStep("fill_credentials", step_fill_credentials),
    PipelineStep("accept_agreements", step_accept_agreements),
    PipelineStep("submit_account", step_submit_account),
    PipelineStep("manual_captcha", step_manual_captcha, manual=True),
    PipelineStep("check_recovery_kit_box", step_check_recovery_kit_box),
    PipelineStep("finish_recovery_kit", step_finish_recovery_kit),
]


def describe_pipeline() -> list[dict]:
    """Step names + whether each runs automatically or needs a human — for
    logging now, and for a future dashboard pipeline-progress view."""
    return [{"name": step.name, "manual": step.manual} for step in PIPELINE_STEPS]


async def run_tuta_signup_pipeline(
    username: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = False,
    on_step: Optional[Callable[[int, PipelineStep], None]] = None,
    wait_for_manual: Optional[Callable[[str], Awaitable[None]]] = None,
    proxy: Optional[ProxyConfig] = None,
    display_name: Optional[str] = None,
    age: Optional[int] = None,
) -> TutaSignupContext:
    """Runs every step in PIPELINE_STEPS in order against a single browser
    context that stays open, unclosed and untouched by any other code, for
    the entire run - from the first goto() to the final click. headless=False
    by default since step_manual_captcha needs a visible window for a human
    to solve the CAPTCHA in.

    Automatic steps are paced with a randomized STEP_DELAY_RANGE pause before
    each one (see _human_delay) instead of firing the instant the previous
    one finishes. The manual=True step doesn't need an extra delay - waiting
    on wait_for_manual already paces it, for as long as that takes; the
    browser is never touched while waiting, so it stays open and visible
    exactly as it is regardless of how the wait is implemented or how long
    it runs.

    on_step(index, step), if given, is called right before each step runs -
    lets a caller (e.g. identity_service, for the pipeline-status endpoint)
    track live progress without this module knowing anything about
    identities or the database.

    wait_for_manual(prompt), if given, replaces the default stdin-based wait
    for the CAPTCHA step - identity_service passes one that waits on an
    asyncio.Event set by a dashboard "Continue" button instead, since a
    backgrounded server process has no interactive stdin to block on.

    proxy, if given, is a Playwright proxy config ({"server": "http://host:port",
    ...}) - identity_service selects and health-checks one from the Proxy
    pool before calling this, so the signup runs from that IP rather than
    the backend machine's own.

    display_name / age, if display_name is given and username isn't, are
    used to derive a human-looking username (see
    generate_username_from_identity) instead of the generic bot-prefixed
    fallback - age lets it pick a plausible birth-year-based suffix some of
    the time instead of always the same random-digits shape."""
    if username is None:
        username = generate_username_from_identity(display_name, age) if display_name else generate_username()
    password = password or generate_password()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, proxy=proxy)
        browser_context = await browser.new_context(locale="cs-CZ", viewport={"width": 1366, "height": 900})
        try:
            ctx = TutaSignupContext(
                username=username,
                password=password,
                context=browser_context,
                wait_for_manual=wait_for_manual or _wait_via_stdin,
                display_name=display_name,
                age=age,
            )
            for index, step in enumerate(PIPELINE_STEPS):
                if not step.manual and index > 0:
                    await _human_delay()
                kind = "MANUAL" if step.manual else "auto"
                ctx.record(f"-> step '{step.name}' [{kind}]")
                if on_step:
                    on_step(index, step)
                await step.fn(ctx)
            ctx.record(f"Account created: {ctx.username}@tuta.com")
            return ctx
        finally:
            # Only ever reached once the loop above is fully done (success)
            # or a step raised - either way the pipeline has finished running,
            # which is the one and only point this closes the window.
            await browser.close()


if __name__ == "__main__":
    print("Pipeline steps:")
    for step in describe_pipeline():
        print(f"  - {step['name']} ({'manual' if step['manual'] else 'automatic'})")
    print()

    result = asyncio.run(run_tuta_signup_pipeline())
    print(f"\nusername: {result.username}")
    print(f"password: {result.password}")
    print(f"email: {result.username}@tuta.com")
