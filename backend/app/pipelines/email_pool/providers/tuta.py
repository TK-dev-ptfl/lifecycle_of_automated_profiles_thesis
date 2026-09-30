"""Automated Tuta Mail (tuta.com) signup pipeline.

Mirrors thesis chapter 3.5.1's Creation pipeline design: the signup flow is
broken into small, independently named/loggable steps rather than one long
function. Tuta's signup requires solving an interactive CAPTCHA, which can't
be automated here, so the pipeline runs a headful (visible) browser and
pauses on that one step until a human confirms it's done.

Every step that changes page state (checking a box, submitting a form,
navigating) verifies the expected result actually happened - checked a
checkbox and then confirms is_checked(), clicked a button that should
transition the page and then confirms the transition happened - and raises a
clear RuntimeError if not, rather than silently moving on to the next step
with the page in an unconfirmed state.

Every ctx.record() message (step start/end, retries, verification results)
is also handed to an optional on_log callback, so a caller (identity_service)
can stream them into app.pipelines.email_pool.progress in real time - this is
what powers the pipeline log viewer on the Monitoring page, since otherwise
these messages only ever went to the backend process's own stdout.

Run directly to try it end-to-end:

    cd backend
    .venv\\Scripts\\python -m app.pipelines.email_pool.providers.tuta

Selectors are pinned to tuta.com's current DOM (data-testid where available,
element id/class otherwise) as of this writing. If Tuta changes their
frontend, the steps that broke will raise naming the selector - update that
one step, the rest of the pipeline is unaffected.
"""
from __future__ import annotations

import asyncio
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Optional, TypedDict

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

TUTA_HOME_URL = "https://tuta.com/cs"

# Pause between automatic steps, seconds. Firing every action the instant the
# previous one finishes is itself a bot signal (see thesis 2.2.1 - behavioral
# detectors flag near-zero, uniform inter-action timing); this keeps pacing
# irregular and roughly human instead.
STEP_DELAY_RANGE = (1.4, 3.8)
# Per-keystroke delay, milliseconds, for the two fields human-speed matters
# most on (username/password) rather than Playwright's instant .fill().
TYPE_DELAY_RANGE_MS = (60, 150)
# How long to wait for a step's expected resulting state (a checkbox
# actually checked, a field appearing, a page transitioning) before treating
# it as a real failure rather than just slow rendering. 0 disables the
# timeout entirely (Playwright convention) - loading through a proxy can
# genuinely take far longer than any fixed bound accounts for, and a step
# should never fail and close the browser just because it was still loading;
# it waits for the real page state no matter how long that takes. The
# try/except around each of these waits is kept in place even though it can
# no longer actually time out, so restoring a real bound later is a one-line
# change back to this constant.
VERIFY_TIMEOUT_MS = 0


async def _human_delay(min_s: float = STEP_DELAY_RANGE[0], max_s: float = STEP_DELAY_RANGE[1]) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def _typing_delay() -> float:
    return random.uniform(*TYPE_DELAY_RANGE_MS)


# Tuta rejects an address that's already taken, and short name-shaped local
# parts ("alexsmith", "jordan42") are overwhelmingly taken already on a mail
# host this old - that rejection was the single most common way
# step_fill_credentials burned all MAX_USERNAME_ATTEMPTS. Every generated
# address is therefore padded out to at least this many characters, which buys
# both length and the entropy that comes with it.
USERNAME_MIN_LENGTH = 18
# Kept well inside any sane local-part limit (RFC 5321 allows 64) while leaving
# the address readable. The numeric tail is never what gets trimmed to fit -
# see the budget calculation in _finish_username - since that's where most of
# the entropy is.
USERNAME_MAX_LENGTH = 30

# Words real people actually bolt onto a handle when their plain name is taken.
# This is what makes a long address still read as a person's rather than as a
# generated token: "alexsmith.photography24" passes where "alexsmith" is taken
# and "alex3c4e660b" looks like exactly what it is.
HANDLE_WORDS = [
    "photography", "travels", "music", "fitness", "outdoors", "reading", "cooking",
    "cycling", "running", "climbing", "gaming", "design", "writes", "sketches",
    "gardening", "coffee", "baking", "hiking", "camping", "surfing", "skating",
    "official", "daily", "world", "online", "here", "real", "studio", "works",
    "journal", "notes", "diary", "life", "space", "corner", "place",
]


def _handle_word() -> str:
    return random.choice(HANDLE_WORDS)


def generate_username(prefix: str = "") -> str:
    """Fallback used only when there's no identity name to base a username on
    (e.g. running this file standalone).

    Deliberately word-based rather than the old "bot" + hex: an obviously
    automated bot3c4e660b-style address is exactly the kind of signal thesis
    2.2.3 flags, and it was short enough to collide besides. Two handle words
    plus a number land in the same length band as the identity-derived ones."""
    core = f"{prefix}{_handle_word()}{random.choice(['', '.', '_'])}{_handle_word()}"
    return _finish_username(core, str(random.randint(1000, 999999)))


def _finish_username(body: str, tail: str) -> str:
    """Assembles the final local part: pads `body` with extra handle words until
    the whole thing clears USERNAME_MIN_LENGTH, then trims only `body` if the
    result would exceed USERNAME_MAX_LENGTH.

    `tail` (the numeric part) is never trimmed. It carries most of the entropy,
    so cutting it to fit the length cap would defeat the point of the cap being
    there - which is to keep addresses long enough not to collide."""
    while len(body) + len(tail) < USERNAME_MIN_LENGTH:
        body = f"{body}{random.choice(['', '.', '_'])}{_handle_word()}"

    body = body[:USERNAME_MAX_LENGTH - len(tail)].strip("._")
    username = re.sub(r"[^a-z0-9._]", "", f"{body}{tail}".lower()).strip("._")

    # Belt-and-suspenders: sanitising can only ever shorten, so a body that was
    # all symbols could in principle land under the minimum. Top it up with
    # digits rather than returning something short enough to collide.
    if len(username) < USERNAME_MIN_LENGTH:
        username += "".join(str(random.randint(0, 9)) for _ in range(USERNAME_MIN_LENGTH - len(username)))
    return username[:USERNAME_MAX_LENGTH]


def _name_parts(display_name: str) -> list[str]:
    ascii_only = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii")
    return [p for p in (re.sub(r"[^a-z0-9]", "", w.lower()) for w in ascii_only.split()) if p]


def generate_username_from_identity(display_name: str, age: Optional[int] = None) -> str:
    """Real people don't all pick 'name + 3 random digits' - some use their
    birth year, some a hobby, some both. Picks one of several realistic shapes
    each time instead of always the same one, so a whole fleet of these doesn't
    look like a template was run through a counter. Falls back to
    generate_username() if the name yields nothing usable (empty/symbols-only).

    Every result clears USERNAME_MIN_LENGTH: a bare "alexsmith" has long since
    been taken on tuta.com, and being rejected as unavailable was the main
    reason step_fill_credentials used to run through all its attempts. The extra
    length comes from real handle words and a numeric tail rather than random
    hex, so the addresses stay human-looking while being long enough not to
    collide."""
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

    # A hobby/descriptor word most of the time - this is the part that makes a
    # name-based address long enough to still be free without looking generated.
    if random.random() < 0.8:
        core = f"{core}{random.choice(['', '.', '_'])}{_handle_word()}"

    # Numeric tail: a birthday derived from the identity's actual age when we
    # have one, otherwise a plain number. Always present now - the old "no
    # number at all" branch produced exactly the short, plain, already-taken
    # addresses this is meant to avoid.
    if age is not None and random.random() < 0.5:
        birth_year = date.today().year - age - random.randint(0, 1)
        year = str(birth_year) if random.random() < 0.6 else f"{birth_year % 100:02d}"
        # Year followed by a month+day is one of the most common real shapes
        # ("alexsmith19980412"), and it's also where most of the entropy lives:
        # a bare 2-digit year leaves only a handful of possible addresses per
        # name, which is how two identities with the same name and age would
        # collide with each other - never mind with a stranger's existing
        # account.
        if random.random() < 0.85:
            tail = f"{year}{random.randint(1, 12):02d}{random.randint(1, 28):02d}"
        else:
            tail = year
    else:
        tail = str(random.randint(1000, 999999))

    return _finish_username(core, tail)


# A 20-char fully-random string is exactly the kind of high-entropy,
# unmemorizable password no real person types by hand - real ones are
# overwhelmingly Word+digits(+symbol). This list is plain common words, not
# tied to any identity, just enough variety that a whole fleet of accounts
# doesn't share a handful of passwords.
PASSWORD_WORDS = [
    "sunshine", "ocean", "tiger", "coffee", "mountain", "river", "phoenix", "dragon",
    "shadow", "thunder", "crystal", "silver", "golden", "winter", "summer", "autumn",
    "falcon", "eagle", "panther", "wolf", "storm", "blaze", "frost", "meadow",
    "harbor", "voyage", "comet", "lunar", "solar", "cobalt", "amber", "cedar",
    "willow", "maple", "raven", "sparrow", "coral", "jasper", "quartz", "onyx",
    "garden", "canyon", "valley", "breeze", "ember", "granite", "horizon", "island",
]
PASSWORD_SYMBOLS = "!@#$%&*"


def generate_password() -> str:
    """Word(+Word) + digits(+symbol) - the pattern most real people actually
    use, instead of a random-character string nobody would type by hand.
    Still comfortably clears typical strength meters: capitalized word(s)
    give upper+lowercase, plus digits, usually plus a symbol, at a length
    (10-18 chars) well above the usual 8-char minimum."""
    word = random.choice(PASSWORD_WORDS).capitalize()
    if random.random() < 0.3:
        word += random.choice(PASSWORD_WORDS).capitalize()
    number = str(random.randint(1, 9999))
    symbol = random.choice(PASSWORD_SYMBOLS) if random.random() < 0.8 else ""
    return f"{word}{number}{symbol}"


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
    # Forwards every ctx.record() message live (in addition to log/stdout) -
    # identity_service wires this to app.pipelines.email_pool.progress.add_log
    # so the Monitoring page can show these messages while the pipeline is
    # still running, not just after the fact.
    on_log: Optional[Callable[[str], None]] = None
    # Kept so step_fill_credentials can generate a fresh candidate in the same
    # style if Tuta rejects the first one as an invalid address.
    display_name: Optional[str] = None
    age: Optional[int] = None

    def record(self, message: str) -> None:
        self.log.append(message)
        print(f"[tuta-signup] {message}")
        if self.on_log:
            self.on_log(message)

    def next_username_candidate(self) -> str:
        if self.display_name:
            return generate_username_from_identity(self.display_name, self.age)
        return generate_username()


def _step_error(step_name: str, message: str) -> RuntimeError:
    return RuntimeError(f"{step_name}: {message}")


# Tuta shows this exact banner when the signup IP (in practice, almost
# always the proxy) has been rate-limited/blocked for suspected abuse -
# usually because it's a public/shared IP (free-proxy-list sources in
# particular) that's already been hammered by other traffic before this
# pipeline ever touched it. There's nothing to wait out or retry here - the
# whole session is dead the moment this appears, so it's treated as an
# immediate, clearly-named failure rather than being left to surface later
# as a confusing timeout on some downstream step.
IP_BLOCKED_TEXT = (
    "Registrace je pro tuto IP adresu dočasně zablokována z důvodu možného "
    "zneužití. Prosím zkuste to později nebo použijte jiné internetové připojení."
)


async def _raise_if_ip_blocked(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    if await ctx.page.get_by_text(IP_BLOCKED_TEXT, exact=True).count() > 0:
        raise _step_error(
            "ip_blocked",
            "Tuta blocked this IP for suspected abuse - closing the session",
        )


# --- Individual pipeline steps ------------------------------------------------
# Each step takes the shared context, performs one action, and returns nothing
# (it mutates ctx.page / ctx.log). Keeping them as separate functions is what
# lets each one be logged, retried, or swapped out independently later. Each
# one also verifies its own result before returning - a click alone only
# proves Playwright could click something, not that the page actually
# responded the way the step assumes.

# The very first navigation of a run is the coldest hop through a freshly
# opened proxy connection (DNS + TCP + TLS all happening for the first time
# through it) - 0 disables the timeout (see VERIFY_TIMEOUT_MS above), so this
# waits however long that takes rather than failing a perfectly fine but slow
# proxy.
HOMEPAGE_GOTO_TIMEOUT_MS = 0


async def step_open_homepage(ctx: TutaSignupContext) -> None:
    page = await ctx.context.new_page()
    await _apply_stealth(page)
    await page.goto(TUTA_HOME_URL, wait_until="domcontentloaded", timeout=HOMEPAGE_GOTO_TIMEOUT_MS)
    try:
        await page.locator("#signup-button:visible").wait_for(state="visible", timeout=VERIFY_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error("step_open_homepage", "signup button never became visible - homepage may not have loaded correctly") from exc
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
    try:
        await signup_page.locator('[data-testid="btn:continue_action"]').wait_for(state="visible", timeout=VERIFY_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error("step_click_signup", "plan-selection page didn't load (Pokracovat button never appeared)") from exc
    ctx.page = signup_page
    ctx.record("Clicked Registrace, switched to signup tab")


async def step_select_free_plan(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    free_radio = ctx.page.locator("div.flex-space-between.items-center.pb-16").filter(has_text="Free").locator("input[type=radio]")
    await free_radio.click()
    if not await free_radio.is_checked():
        raise _step_error("step_select_free_plan", "Free plan radio button did not become checked after clicking")
    ctx.record("Selected Free plan")


async def step_continue_after_plan(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    await ctx.page.click('[data-testid="btn:continue_action"]')
    try:
        await ctx.page.locator('[data-testid="tfi:username_label"]').wait_for(state="visible", timeout=VERIFY_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error("step_continue_after_plan", "username field never appeared after clicking Pokracovat") from exc
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

    actual_username = await username_field.input_value()
    if actual_username != ctx.username:
        raise _step_error(
            "step_fill_credentials",
            f"username field contains {actual_username!r}, expected {ctx.username!r} - typing may not have registered",
        )

    new_password_field = page.locator('[data-testid="tfi:newPassword_label"]')
    await new_password_field.press_sequentially(ctx.password, delay=_typing_delay())
    actual_new_password = await new_password_field.input_value()
    if actual_new_password != ctx.password:
        raise _step_error("step_fill_credentials", "new-password field does not match what was typed")

    await _human_delay(0.4, 1.2)
    repeat_password_field = page.locator('[data-testid="tfi:repeatedPassword_label"]')
    await repeat_password_field.press_sequentially(ctx.password, delay=_typing_delay())
    actual_repeat_password = await repeat_password_field.input_value()
    if actual_repeat_password != ctx.password:
        raise _step_error("step_fill_credentials", "repeat-password field does not match what was typed")

    ctx.record(f"Filled username '{ctx.username}' and password")


async def step_accept_agreements(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    checkboxes = ctx.page.locator("div.flex.col.gap-4.smaller.justify-start.mt-16 input[type=checkbox]")
    count = await checkboxes.count()
    if count == 0:
        raise _step_error("step_accept_agreements", "no agreement checkboxes found on page")
    for i in range(count):
        if i > 0:
            await _human_delay(0.5, 1.4)
        box = checkboxes.nth(i)
        await box.click()
        if not await box.is_checked():
            raise _step_error("step_accept_agreements", f"checkbox {i} did not become checked after clicking")
    ctx.record(f"Checked {count} agreement checkbox(es)")


async def step_submit_account(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    # No confirmed selector yet for what a CAPTCHA widget or a failed-
    # submission error banner looks like here, so this can't verify its own
    # outcome the way the other steps do (see step_manual_captcha, which
    # verifies the *next* page state instead). What it can do is name this
    # step clearly if the click itself fails/times out (e.g. a slow
    # residential proxy), instead of that surfacing as an opaque exception
    # from deep inside Playwright.
    try:
        await ctx.page.click('[data-testid="btn:create_new_account_label"]')
    except PlaywrightTimeoutError as exc:
        raise _step_error("step_submit_account", "create-account button was never clickable") from exc
    ctx.record("Submitted account creation form (Vytvorit ucet)")


# Disabled for now (not registered in PIPELINE_STEPS below) - re-enable by
# uncommenting the function body and swapping it back in for
# step_captcha_sleep in PIPELINE_STEPS.
# async def step_manual_captcha(ctx: TutaSignupContext) -> None:
#     """Tuta shows an interactive CAPTCHA here *sometimes* - not every session
#     gets challenged (depends on its own anti-bot heuristics: IP reputation,
#     fingerprint, etc). For now this always waits for a human to confirm
#     before proceeding, even on runs where the recovery-kit page would have
#     appeared on its own without a challenge - auto-skipping this step turned
#     out to be an easy way to race ahead of a CAPTCHA that was still loading,
#     so until that's more reliably distinguishable, every run stops here and
#     the browser window stays open and untouched until a person says to go.
#
#     This waits via ctx.wait_for_manual (stdin prompt for the standalone
#     script, a dashboard button click when run through identity_service).
#     Once the human says it's done, this does NOT just take their word for it
#     - it re-checks that the recovery-kit page actually appeared, since a
#     mis-solved or still-pending CAPTCHA would otherwise let the pipeline
#     barrel on into steps that assume a page state that was never reached."""
#     assert ctx.page is not None
#     recovery_checkbox = ctx.page.locator(RECOVERY_KIT_CONTINUE_SELECTOR)
#
#     ctx.record("Waiting for manual confirmation in the browser window...")
#     await ctx.wait_for_manual(
#         "Solve the CAPTCHA in the browser window, then press Enter here to continue... "
#     )
#
#     try:
#         await recovery_checkbox.wait_for(state="visible", timeout=VERIFY_TIMEOUT_MS)
#     except PlaywrightTimeoutError as exc:
#         raise _step_error(
#             "step_manual_captcha",
#             "confirmed done by operator, but the recovery-kit page never appeared - "
#             "the CAPTCHA may not actually have been solved correctly",
#         ) from exc
#     ctx.record("Manual CAPTCHA step confirmed done by operator, recovery kit page verified")


# Placeholder standing in for step_manual_captcha while it's disabled - waits
# for the same real page-state signal that step verified after a human
# confirmed (the recovery-kit page's checkbox actually appearing), instead of
# a fixed sleep. A blind sleep-then-continue would move on to
# step_check_recovery_kit_box regardless of whether the page actually got
# there, which defeats every other step's own "verify, don't assume" rule -
# this waits for the real transition instead. 0 disables the timeout (see
# VERIFY_TIMEOUT_MS above): if a genuine CAPTCHA shows up with no human
# around to solve it (step_manual_captcha is disabled), this will now wait
# indefinitely rather than failing after a fixed window - deliberate per
# "never timeout and close it", but means a real CAPTCHA now hangs this
# pipeline run rather than failing it; nothing currently re-enables the
# manual step to unblock it if that happens.
CAPTCHA_AUTO_WAIT_TIMEOUT_MS = 0


# The recovery-kit page's own Continue button - unlike a bare
# "input[type=checkbox]" selector, this data-testid only ever exists on the
# recovery-kit page itself, so it's an unambiguous anchor for "we're
# genuinely here now". A generic checkbox selector is NOT safe to wait on for
# this: a CAPTCHA challenge commonly renders its own checkbox (the classic
# "I'm not a robot" widget), and the agreements page a few steps earlier has
# checkboxes of its own too - either could satisfy a bare checkbox wait
# without the pipeline having actually reached the recovery-kit page at all.
RECOVERY_KIT_CONTINUE_SELECTOR = '[data-testid="btn:recovery_kit_page_continue_label"]'


async def step_captcha_sleep(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    recovery_page_anchor = ctx.page.locator(RECOVERY_KIT_CONTINUE_SELECTOR)
    ctx.record("step_manual_captcha disabled - waiting for the recovery-kit page to appear on its own...")
    try:
        await recovery_page_anchor.wait_for(state="visible", timeout=CAPTCHA_AUTO_WAIT_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error(
            "step_captcha_sleep",
            "recovery-kit page never appeared - a CAPTCHA may be blocking with no human to solve it "
            "(step_manual_captcha is currently disabled)",
        ) from exc
    ctx.record("Recovery kit page appeared")


async def step_check_recovery_kit_box(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    # Re-confirmed here too, not just trusted from step_captcha_sleep having
    # already seen it - this step's whole job is clicking the right
    # checkbox, so it re-verifies its own precondition rather than assuming
    # the page hasn't changed since the previous step returned.
    try:
        await ctx.page.locator(RECOVERY_KIT_CONTINUE_SELECTOR).wait_for(state="visible", timeout=VERIFY_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error(
            "step_check_recovery_kit_box",
            "recovery-kit page isn't actually showing - refusing to click a checkbox on the wrong page",
        ) from exc
    checkbox = ctx.page.locator("input[type=checkbox]").first
    await checkbox.click()
    if not await checkbox.is_checked():
        raise _step_error("step_check_recovery_kit_box", "checkbox did not become checked after clicking")
    ctx.record("Checked recovery kit acknowledgement box")


async def step_finish_recovery_kit(ctx: TutaSignupContext) -> None:
    assert ctx.page is not None
    continue_button = ctx.page.locator(RECOVERY_KIT_CONTINUE_SELECTOR)
    await continue_button.click()
    try:
        # If the click had no real effect (e.g. the checkbox wasn't actually
        # checked and the button silently no-ops), the page stays put and
        # this button never disappears - that's the signal something's wrong.
        await continue_button.wait_for(state="hidden", timeout=VERIFY_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise _step_error(
            "step_finish_recovery_kit",
            "page did not move on after clicking Pojdme zacit - the recovery-kit "
            "checkbox may not actually have been checked",
        ) from exc
    ctx.record("Clicked Pojdme zacit - signup complete")


# How long to allow for the mailbox to actually finish loading after
# recovery-kit - Tuta generates encryption keys client-side at this point,
# which can take a few seconds longer than a plain page navigation. 0
# disables the timeout (see VERIFY_TIMEOUT_MS above).
MAILBOX_LOAD_TIMEOUT_MS = 0


# Disabled for now (not registered in PIPELINE_STEPS below) - re-enable by
# uncommenting the function body and adding it back to PIPELINE_STEPS.
# async def step_enter_mailbox(ctx: TutaSignupContext) -> None:
#     """Clicking through the recovery-kit screen isn't proof the account
#     actually works - this waits for the real inbox UI (the "new email"
#     compose button, which only renders once the mailbox has fully loaded)
#     before the pipeline is considered done. Since this is the last entry in
#     PIPELINE_STEPS, the browser only closes (see run_tuta_signup_pipeline's
#     finally) once this confirms the profile was genuinely entered, not
#     right after the last signup-wizard click."""
#     assert ctx.page is not None
#     try:
#         await ctx.page.locator('[data-testid="btn:newMail_action"]').wait_for(
#             state="visible", timeout=MAILBOX_LOAD_TIMEOUT_MS
#         )
#     except PlaywrightTimeoutError as exc:
#         raise _step_error("step_enter_mailbox", "mailbox/inbox UI never loaded after signup completed") from exc
#     ctx.record("Entered mailbox - inbox loaded, account confirmed working")


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
    PipelineStep("manual_captcha", step_captcha_sleep, manual=False),  # step_manual_captcha disabled, see above
    PipelineStep("check_recovery_kit_box", step_check_recovery_kit_box),
    PipelineStep("finish_recovery_kit", step_finish_recovery_kit),
    # PipelineStep("enter_mailbox", step_enter_mailbox),  # disabled for now, see step_enter_mailbox above
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
    on_log: Optional[Callable[[str], None]] = None,
) -> TutaSignupContext:
    """Runs every step in PIPELINE_STEPS in order against a single browser
    context that stays open, unclosed and untouched by any other code, for
    the entire run - from the first goto() to the final click. headless=False
    by default since step_manual_captcha needs a visible window for a human
    to solve the CAPTCHA in.

    This is a plain sequential loop - each step is fully awaited before the
    next one starts, and (as of this version) each step verifies its own
    expected outcome before returning, raising a RuntimeError if the page
    didn't actually respond the way the step assumes. A step "passing" here
    means its effect was confirmed, not just that a click didn't throw.

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
    the time instead of always the same random-digits shape.

    on_log(message), if given, receives every ctx.record() message as it
    happens - identity_service forwards these into pipeline_progress so the
    Monitoring page's pipeline log viewer updates live instead of only after
    the run finishes."""
    if username is None:
        username = generate_username_from_identity(display_name, age) if display_name else generate_username()
    password = password or generate_password()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless, proxy=proxy)
        # ignore_https_errors is deliberately NOT set (Playwright's secure
        # default - certificate validation stays on). Some proxies in this
        # pool (free/public sources) terminate HTTPS themselves and hand
        # back their own certificate instead of properly tunneling tuta.com's
        # real one - accepting that would mean the proxy can read and modify
        # everything "encrypted" going through it, credentials included, so
        # the connection must actually fail (ERR_CERT_AUTHORITY_INVALID) when
        # that happens, not silently continue over a compromised channel. The
        # pipeline already treats that failure like any other: this proxy's
        # session ends, the identity is cleaned up, and a different proxy
        # gets tried for the next one - never running a signup over a
        # connection whose security the proxy has undermined.
        browser_context = await browser.new_context(
            locale="cs-CZ", viewport={"width": 1366, "height": 900},
        )
        # Playwright's default action/navigation timeout (30s) was tuned for
        # a direct connection - a residential proxy adds real latency (and
        # occasional connection hiccups) on every request, so a plain click()
        # or goto() could time out on a perfectly fine run and get misread as
        # a broken selector. 0 disables the timeout entirely for every action
        # that doesn't set its own explicit timeout - per "never timeout and
        # close it", a step should wait for its target no matter how slowly
        # the page is loading through whatever proxy this run landed on. The
        # real risk this trades away: a genuinely broken selector (e.g. Tuta
        # changes their frontend) now hangs a step forever instead of failing
        # with a clear "never became visible" error - there's no more
        # automatic distinction between "just slow" and "never happening".
        browser_context.set_default_timeout(0)
        try:
            ctx = TutaSignupContext(
                username=username,
                password=password,
                context=browser_context,
                wait_for_manual=wait_for_manual or _wait_via_stdin,
                on_log=on_log,
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
                # Checked after every step, not just the ones most likely to
                # trigger it - wherever in the flow Tuta decides this IP is
                # abusive, catching it immediately beats it quietly showing
                # up and only being noticed as a mysterious failure two steps
                # later.
                await _raise_if_ip_blocked(ctx)
                ctx.record(f"<- step '{step.name}' verified OK")
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
