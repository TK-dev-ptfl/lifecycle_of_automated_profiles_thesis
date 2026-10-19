"""Running a behaviour algorithm against a page, on demand, from the dashboard.

The Algorithm page can start one of these and watch it work. A run opens a real
browser on the machine hosting the backend, drives it with app.behaviour, and
reports three things: what the algorithm read, how it behaved, and - when the
target page scores sessions, as the feed lab does - what the page made of it.

Scenarios are the site-specific half. A scenario is a URL plus a FeedSchema;
everything else (the primitives, the profile, the executor) is shared. Adding a
site means adding a scenario, which is the same claim the behaviour layer makes
everywhere else.

Progress lives in memory, like the email pipeline's: a run lives and dies with
this process, so there is nothing to persist.
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from app.behaviour.adapters.playwright_env import PlaywrightEnvironment
from app.behaviour.environment import Target
from app.behaviour.evaluation import detectors, mouse_model
from app.behaviour.evaluation.trace_stats import trace_stats
from app.behaviour.executor import Actor
from app.behaviour.fingerprint import (
    fingerprint_for,
    launch as launch_fingerprinted,
    new_context as fingerprinted_context,
    read_real_browser,
)
from app.behaviour.goals import ClickOn, Dwell, FeedSchema, ReadFeed, ScrollTo, TypeInto, Wander
from app.behaviour.profile import derive_for
from app.behaviour.robotic import RoboticActor
from app.services import run_proxy_service

MAX_LOG_LINES = 400
# Bump when what a run asks of the driver changes, so results recorded under
# different tasks are never pooled (compare_runs --aggregate filters on it).
#   1  feed lab: the human-like style only read; the robotic one also clicked and typed
#   2  every style performs FEED_TASK (read, like, comment, post)
PROTOCOL = 2
# A browsing run is minutes at most; past this something is wedged and the
# browser needs closing rather than leaving on the host indefinitely.
RUN_TIMEOUT_S = 900
# Screenshots and traces from each run, one folder per run id (gitignored).
RUNS_DIR = Path(__file__).resolve().parents[2] / "tests" / "behaviour" / "test_env" / "runs"


@dataclass(frozen=True)
class Scenario:
    """One page this algorithm knows how to read, and how to read it."""

    key: str
    name: str
    description: str
    url: str
    schema: FeedSchema
    # JS that pulls a session score out of the page, when it has one. Optional:
    # most sites do not grade you to your face.
    score_js: Optional[str] = None
    # How the page is driven: "human" is app.behaviour's Actor; "robotic" is
    # the deliberately bot-like RoboticActor, the negative control; "manual" is
    # a real person at the keyboard, the reference both are compared against.
    # Same identity, fingerprint and proxy in all three, so only the driving
    # differs.
    style: str = "human"


# The feed lab scores the session it is being read by, which makes it the one
# target where the behaviour layer gets marked rather than merely exercised.
FEED_LAB_SCORE_JS = """
() => {
  const row = id => {
    const el = document.querySelector(id);
    if (!el) return null;
    return { value: el.querySelector('.v')?.textContent?.trim(),
             detail: el.querySelector('.sub')?.textContent?.trim() };
  };
  const checks = [...document.querySelectorAll('#detail .chk')].map(li => ({
    state: li.dataset.s,
    name: li.querySelector('b')?.textContent?.trim(),
    detail: li.querySelector('p')?.textContent?.trim(),
  }));
  return {
    overall: document.querySelector('#scNum')?.textContent?.trim(),
    verdict: document.querySelector('#scVerdict')?.textContent?.trim(),
    behaviour: row('#rBeh'), fingerprint: row('#rFp'), recaptcha: row('#rRc'),
    checks,
  };
}
"""

@dataclass(frozen=True)
class FeedTask:
    """What every style is asked to do in the feed, so they are graded on the
    same acts.

    A comparison only means something when the human-like run, the robotic
    control and the manual session perform the same task. If one of them never
    clicks or types, the lab's click and keystroke checks stay "pending" for it
    and it is scored on fewer, easier signals than the others.
    """

    likes: int = 3
    comment: str = "Great post, thanks for sharing"
    post: str = "Lovely slow morning walk along the river today"

    def describe(self, want: int) -> str:
        return (f"read {want} posts, like {self.likes} of them, write one comment "
                "and publish one post")


FEED_TASK = FeedTask()

FEED_LAB_SCHEMA = FeedSchema(
    item=Target("article.post", "feed posts"),
    fields={
        "author": ".who-line b",
        "handle": ".who-line span",
        "body": "p.text",
        "likes": ".act.like span",
        "comments": ".act.cmt-btn span",
        "reposts": ".act.rep span",
    },
)

SCENARIOS: dict[str, Scenario] = {
    "feed-lab": Scenario(
        key="feed-lab",
        name="Feed lab — read posts",
        description=(
            "Reads a feed the way a person does, against the local lab at "
            "tests/behaviour/test_env/feed-lab (start it with: node server.mjs). "
            "The lab grades the session, so this run comes back with a score."
        ),
        url="http://localhost:8080/",
        schema=FEED_LAB_SCHEMA,
        score_js=FEED_LAB_SCORE_JS,
    ),
    "feed-lab-bot": Scenario(
        key="feed-lab-bot",
        name="Feed lab — robotic control",
        description=(
            "The same lab, identity, fingerprint and proxy, driven like a naive "
            "script: instant start, straight constant-speed moves, dead-centre "
            "zero-hold clicks, script scrolling on a fixed beat, a JavaScript "
            "click, metronome typing and a filled field. Should fail the "
            "behaviour checks while the fingerprint still passes."
        ),
        url="http://localhost:8080/",
        schema=FEED_LAB_SCHEMA,
        score_js=FEED_LAB_SCORE_JS,
        style="robotic",
    ),
    "feed-lab-manual": Scenario(
        key="feed-lab-manual",
        name="Feed lab — you drive (manual)",
        description=(
            "No algorithm: the browser opens with the same identity, fingerprint and "
            "proxy, and you browse the feed by hand. Do the same task as the "
            "algorithm: read about 8 posts, like 3 of them, write one comment and "
            "publish one post. Then click 'Finish session' in the lab panel. The "
            "session is judged exactly like the others, as the human reference."
        ),
        url="http://localhost:8080/?manual=1",
        schema=FEED_LAB_SCHEMA,
        score_js=FEED_LAB_SCORE_JS,
        style="manual",
    ),
}


def feed_task_goals(read: int, task: FeedTask) -> list:
    """FEED_TASK as goals for the human-like Actor, once `read` posts are read.

    Likes go to the last posts read, which are the ones still near the screen,
    and the comment to the last of all - a person acts on what is in front of
    them rather than scrolling back up to the start. The post is written last,
    in the composer at the top, as the robotic control does too.
    """
    if read == 0:
        return []
    post = lambda i: f"#feed > article.post:nth-child({i})"  # noqa: E731 - 1-based, like nth-child
    goals: list = []
    for i in range(max(1, read - task.likes + 1), read + 1):
        like = Target(f"{post(i)} .act.like", f"like on post {i}")
        goals += [ScrollTo(like), Dwell(reason="deciding whether to like it"), ClickOn(like)]
    last = post(read)
    open_comments = Target(f"{last} .act.cmt-btn", f"comments on post {read}")
    field = Target(f"{last} .reply-in", "comment field")
    send = Target(f"{last} .send", "reply button")
    # Opening the comments pushes the field down, often below the fold, so each
    # target is scrolled to first (a no-op when it is already on screen).
    goals += [
        ScrollTo(open_comments), ClickOn(open_comments),
        ScrollTo(field), TypeInto(field, task.comment),
        ScrollTo(send), ClickOn(send),
        Dwell(reason="looking at the comment"),
    ]
    composer = Target("#composer", "post composer")
    post_button = Target("#postBtn", "post button")
    goals += [
        ScrollTo(composer),
        TypeInto(composer, task.post),
        ScrollTo(post_button), ClickOn(post_button),
        Dwell(reason="checking the post went up"),
    ]
    return goals


@dataclass
class BehaviourRun:
    """Live state of one run, as the dashboard polls it."""

    id: str
    scenario: str
    identity: str
    url: str
    want: int
    headless: bool
    # Draw the simulated pointer in the page (debug only; see fingerprint.new_context).
    show_cursor: bool = False
    # Go out through a proxy from the list (run_proxy_service). On by default:
    # a test run on the host's own address says nothing about how an identity
    # behind a proxy is received.
    use_proxy: bool = True
    # After the session: score the mouse trace with the trained classifier and
    # run the vendored detectors (rebrowser, CreepJS) in the same browser.
    evaluate: bool = True
    # Also visit public detector pages. Opt-in, and only behind a proxy: they
    # log their visitors.
    public_checks: bool = False
    # Manual sessions end when the person clicks Finish, or after this long.
    manual_minutes: float = 10.0
    protocol: int = PROTOCOL
    status: str = "running"          # running | completed | failed
    profile: dict = field(default_factory=dict)
    # The machine and browser the identity presented (behaviour.fingerprint).
    fingerprint: dict = field(default_factory=dict)
    # The proxy used and where it exits; no credentials.
    proxy: dict = field(default_factory=dict)
    # What the independent judges concluded: {"mouse_model", "rebrowser", "creepjs", "public"}.
    evaluation: dict = field(default_factory=dict)
    # Raw input measurements (evaluation.trace_stats), for side-by-side comparison.
    stats: dict = field(default_factory=dict)
    style: str = "human"
    artifacts_dir: Optional[str] = None
    logs: list[str] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    score: Optional[dict] = None
    error: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    elapsed_s: float = 0.0

    def log(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.logs.append(f"{stamp} {message}")
        if len(self.logs) > MAX_LOG_LINES:
            del self.logs[: len(self.logs) - MAX_LOG_LINES]

    def as_dict(self) -> dict:
        return {
            "id": self.id, "scenario": self.scenario, "identity": self.identity,
            "url": self.url, "want": self.want, "headless": self.headless,
            "show_cursor": self.show_cursor, "use_proxy": self.use_proxy, "proxy": self.proxy,
            "evaluate": self.evaluate, "public_checks": self.public_checks,
            "evaluation": self.evaluation, "artifacts_dir": self.artifacts_dir,
            "stats": self.stats, "style": self.style, "manual_minutes": self.manual_minutes,
            "protocol": self.protocol, "status": self.status, "profile": self.profile,
            "fingerprint": self.fingerprint, "logs": self.logs,
            "items": self.items, "score": self.score, "error": self.error,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "elapsed_s": round(self.elapsed_s, 1),
        }


_runs: dict[str, BehaviourRun] = {}


def list_scenarios() -> list[dict]:
    return [
        {"key": s.key, "name": s.name, "description": s.description, "url": s.url,
         "fields": list(s.schema.fields), "style": s.style}
        for s in SCENARIOS.values()
    ]


def _saved_runs() -> dict[str, dict]:
    """Finished runs saved by earlier processes (RUNS_DIR/<id>/run.json)."""
    saved = {}
    if RUNS_DIR.exists():
        for path in RUNS_DIR.glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                saved[data["id"]] = data
            except Exception:
                continue
    return saved


def _save(run: BehaviourRun) -> None:
    try:
        out = RUNS_DIR / run.id
        out.mkdir(parents=True, exist_ok=True)
        (out / "run.json").write_text(json.dumps(run.as_dict(), indent=1), encoding="utf-8")
    except Exception as exc:
        print(f"[behaviour-run {run.id}] could not save: {exc}")


def get_run(run_id: str) -> Optional[dict]:
    run = _runs.get(run_id)
    if run:
        return run.as_dict()
    return _saved_runs().get(run_id)


def list_runs(limit: int = 10) -> list[dict]:
    """Newest first: this process's runs, then finished ones saved on disk, so
    a comparison can span backend restarts."""
    merged = {**_saved_runs(), **{r.id: r.as_dict() for r in _runs.values()}}
    newest = sorted(merged.values(), key=lambda r: r.get("started_at", ""), reverse=True)
    return newest[:limit]


def start_run(
    scenario_key: str,
    *,
    identity: str,
    want: int,
    headless: bool,
    url: Optional[str] = None,
    show_cursor: bool = False,
    use_proxy: bool = True,
    evaluate: bool = True,
    public_checks: bool = False,
    manual_minutes: float = 10.0,
) -> BehaviourRun:
    """Creates the run record and schedules it. Returns immediately - the browser
    takes tens of seconds, which no HTTP request should wait on."""
    scenario = SCENARIOS[scenario_key]
    target = url or scenario.url
    if scenario.style == "manual" and "manual" not in urlsplit(target).query:
        # The lab only shows its Finish button with ?manual, whatever host it is on.
        target += ("&" if urlsplit(target).query else "?") + "manual=1"
    run = BehaviourRun(
        id=str(uuid.uuid4()),
        scenario=scenario.key,
        identity=identity,
        url=target,
        want=want,
        show_cursor=show_cursor,
        use_proxy=use_proxy,
        evaluate=evaluate,
        public_checks=public_checks,
        manual_minutes=manual_minutes,
        style=scenario.style,
        # A manual session needs a window to drive.
        headless=False if scenario.style == "manual" else headless,
    )
    _runs[run.id] = run
    asyncio.create_task(_execute(run, scenario), name=f"behaviour-run:{run.id}")
    return run


async def _execute(run: BehaviourRun, scenario: Scenario) -> None:
    # A manual session lasts as long as the person wants, up to their limit,
    # plus time for the judges afterwards.
    limit = run.manual_minutes * 60 + 600 if scenario.style == "manual" else RUN_TIMEOUT_S
    try:
        await asyncio.wait_for(_drive(run, scenario), timeout=limit)
    except asyncio.TimeoutError:
        run.status = "failed"
        run.error = f"run exceeded {limit:.0f}s and was stopped"
        run.log(run.error)
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.log(run.error)
        print(f"[behaviour-run {run.id}] failed:\n{traceback.format_exc()}")
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()
        _save(run)


async def _drive(run: BehaviourRun, scenario: Scenario) -> None:
    # Imported here rather than at module import: the backend should start fine
    # on a machine where Playwright's browsers were never installed, and only
    # fail when someone actually asks for a run.
    from playwright.async_api import async_playwright

    profile = derive_for(run.identity)
    run.profile = {
        "typing_wpm": round(profile.typing_wpm),
        "key_hold_ms": round(profile.key_hold_ms),
        "hesitancy": round(profile.hesitancy, 2),
        "aim_scatter": round(profile.aim_scatter, 2),
        "path_curviness": round(profile.path_curviness, 2),
        "restlessness": round(profile.restlessness, 2),
        "reads_with_cursor": round(profile.reads_with_cursor, 2),
        "patience_s": round(profile.patience_s),
        "wander_range": list(profile.wander_range),
    }
    run.log(f"persona {run.identity}: {run.profile}")

    proxy = None
    if run.use_proxy:
        proxy = await run_proxy_service.choose(run.identity, log=run.log)
        run.proxy = proxy.summary()
        run.log(
            f"proxy {proxy.label} ({proxy.kind}) exits at {proxy.exit_ip}, "
            f"{proxy.country_code}, {proxy.timezone}"
            + (" - flagged as a hosting address" if proxy.flagged_hosting else "")
        )
    else:
        run.log("no proxy - going out on this machine's own address")

    async with async_playwright() as pw:
        # The machine comes from the same identity key as the persona: the
        # browser it claims is the browser launched, and everything else is
        # presented through that browser's own settings. See behaviour.fingerprint.
        # Behind a proxy, language and clock follow the proxy's exit.
        fp = fingerprint_for(
            run.identity,
            country_code=proxy.country_code if proxy else None,
            timezone=proxy.timezone if proxy else None,
        )
        browser, fp = await launch_fingerprinted(
            pw, fp, headless=run.headless, log=run.log,
            proxy=proxy.playwright if proxy else None,
        )
        try:
            fp = fp.bind(await read_real_browser(browser))
            run.fingerprint = fp.summary()
            run.log(
                f"fingerprint: {run.fingerprint['browser']} on {fp.os}, "
                f"screen {run.fingerprint['screen']}, viewport {run.fingerprint['viewport']}, "
                f"{fp.locale}, {fp.timezone}"
            )
            context = await fingerprinted_context(browser, fp, show_cursor=run.show_cursor)
            if run.show_cursor:
                run.log("cursor overlay on - the page can see it; for watching only")
            # A fresh temporary profile has no cookies to begin with; cleared
            # anyway so that stays true whatever the read above left behind.
            await context.clear_cookies()
            run.log("fresh browser profile, no cookies")
            page = await context.new_page()

            run.log(f"opening {run.url}")
            await page.goto(run.url, wait_until="domcontentloaded", timeout=30_000)
            try:
                await page.wait_for_selector(scenario.schema.item.query, timeout=15_000)
            except Exception as exc:
                raise RuntimeError(
                    f"no {scenario.schema.item} on {run.url} - is the target running?"
                ) from exc

            started = time.monotonic()
            if scenario.style == "manual":
                run.log(
                    f"your turn: {FEED_TASK.describe(run.want)} in the browser window, "
                    f"then click 'Finish session' in the lab panel (limit {run.manual_minutes:g} min)"
                )
                try:
                    await page.wait_for_function(
                        "() => window.__hearthFinished === true",
                        timeout=run.manual_minutes * 60_000, polling=1000,
                    )
                    run.log("finished by the person")
                except Exception:
                    run.log(f"time limit of {run.manual_minutes:g} min reached - collecting results")

                async def click(query: str, _label: str) -> None:
                    raise RuntimeError("a manual session is never clicked by the runner")
                pause = asyncio.sleep
            elif scenario.style == "robotic":
                robot = RoboticActor(page, log=run.log)
                run.log("driving robotically - the negative control")
                run.items = await robot.read_feed(scenario.schema, run.want, FEED_TASK)

                async def click(query: str, _label: str) -> None:
                    await robot.click(query)
                pause = asyncio.sleep
            else:
                env = PlaywrightEnvironment(page)
                actor = Actor(env=env, profile=profile, log=run.log)
                await actor.pursue([
                    Dwell(reason="taking in the page"),
                    Wander(reason="settling in before reading"),
                    ReadFeed(scenario.schema, want=run.want),
                ])
                run.items = list(actor.collected)
                await actor.pursue(feed_task_goals(len(run.items), FEED_TASK))

                async def click(query: str, label: str) -> None:
                    await actor.pursue([ClickOn(Target(query, label))])

                async def pause(seconds: float) -> None:
                    await actor.pursue([Dwell(seconds=seconds, reason="glancing at the session check")])
            run.elapsed_s = time.monotonic() - started

            # Read the input trace now, before the score tabs are clicked, so
            # the classifier judges the session and not the measurement.
            out_dir = RUNS_DIR / run.id
            out_dir.mkdir(parents=True, exist_ok=True)
            run.artifacts_dir = str(out_dir)
            trace = await page.evaluate("() => window.__hearthTrace ? window.__hearthTrace() : null")
            if trace:
                (out_dir / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
                run.stats = trace_stats(trace)

            if scenario.score_js:
                run.score = await _read_score(page, click, pause, run.log, scenario.score_js)
                if run.score:
                    run.log(
                        f"page scored the session {run.score.get('overall')} "
                        f"({run.score.get('verdict')})"
                    )

            if run.evaluate:
                await _evaluate(run, context, trace, Path(run.artifacts_dir))

            run.status = "completed"
            run.log(f"read {len(run.items)} item(s) in {run.elapsed_s:.0f}s")
        finally:
            await browser.close()


async def _read_score(page, click, pause, log, score_js: str) -> Optional[dict]:
    """Reads the page's verdict, including every check from both detail tabs.

    The tabs are opened by whatever drove the session, in its own manner - the
    human actor with its hand, the robotic one with its dead-centre click. An
    out-of-character click at the end would be scored too, and would move the
    result for the measurement itself. Each tab shows only its own checks, so
    the two lists are read one after the other and merged.
    """
    await pause(1.2)
    # The lab's own read-out, when it has one: no clicks, so nothing is added
    # to the session being measured - essential in a manual session, where the
    # runner must not touch the input at all.
    report = await page.evaluate("() => window.__hearthReport ? window.__hearthReport() : null")
    if report:
        return report
    checks: list[dict] = []
    score: Optional[dict] = None
    for tab, label in (("beh", "behaviour details"), ("fp", "fingerprint details")):
        try:
            await click(f'[data-tab="{tab}"]', label)
            await page.wait_for_timeout(700)
        except Exception as exc:
            log(f"could not open {label}: {exc}")
            continue
        score = await page.evaluate(score_js)
        for check in (score or {}).get("checks", []):
            checks.append({**check, "group": tab})
    if score is None:
        score = await page.evaluate(score_js)
    if score is not None:
        score["checks"] = checks
    return score


async def _evaluate(run: BehaviourRun, context, trace: Optional[dict], out_dir: Path) -> None:
    """The independent judges, after the session: the trained mouse classifier
    on the recorded trace, then the vendored detectors in fresh tabs of the same
    browser. Each is reported separately and none can fail the run - a judge
    that breaks is recorded as broken, the run still stands."""
    if not mouse_model.model_available():
        run.evaluation["mouse_model"] = {"verdict": "no model - run bot_model/train.py"}
    else:
        run.evaluation["mouse_model"] = mouse_model.score_trace(trace)
        m = run.evaluation["mouse_model"]
        run.log(
            f"mouse classifier: {m.get('verdict')}"
            + (f", bot probability {m['bot_probability']} over {m['strokes']} strokes" if "bot_probability" in m else "")
        )

    parts = urlsplit(run.url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if not await detectors.vendor_available(context, origin):
        note = f"{origin} does not serve /vendor/ - restart the feed lab (node server.mjs) to get the detectors"
        run.evaluation["rebrowser"] = run.evaluation["creepjs"] = {"error": note}
        run.log(note)
    else:
        for name, judge in (("rebrowser", detectors.run_rebrowser), ("creepjs", detectors.run_creepjs)):
            try:
                run.evaluation[name] = await judge(context, origin, out_dir)
            except Exception as exc:
                run.evaluation[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        rb, cj = run.evaluation["rebrowser"], run.evaluation["creepjs"]
        if "detected" in rb:
            run.log(f"rebrowser: {len(rb['detected'])} leak(s) detected" + (f" - {', '.join(rb['detected'])}" if rb["detected"] else ""))
        if "headless" in cj:
            run.log(
                f"creepjs: headless {cj['headless']}%, like headless {cj['like_headless']}%, "
                f"stealth {cj['stealth']}%, {cj['lie_count']} lie(s)"
            )

    if run.public_checks:
        if not run.use_proxy:
            run.evaluation["public"] = [{"error": "skipped - public pages are only visited through a proxy"}]
            run.log("public checks skipped: they record visitors, and this run has no proxy")
        else:
            run.evaluation["public"] = await detectors.run_public(context, out_dir, log=run.log)


# --- comparison ----------------------------------------------------------------

# Rows of the comparison, as (section, label, getter on a run dict). Every run
# gets the same rows, so a human-driven session, the algorithm and the robotic
# control line up value against value.
def _get(*path):
    def read(run: dict):
        value = run
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value
    return read


_COMPARE_ROWS = [
    ("lab", "overall", _get("score", "overall")),
    ("lab", "verdict", _get("score", "verdict")),
    ("lab", "behaviour", _get("score", "behaviour", "value")),
    ("lab", "fingerprint", _get("score", "fingerprint", "value")),
    ("lab", "reCAPTCHA v3", _get("score", "recaptcha", "value")),
    ("classifier", "verdict", _get("evaluation", "mouse_model", "verdict")),
    ("classifier", "bot probability", _get("evaluation", "mouse_model", "bot_probability")),
    ("classifier", "bot-like strokes", lambda r: (
        f"{_get('evaluation', 'mouse_model', 'bot_like_strokes')(r)}/{_get('evaluation', 'mouse_model', 'strokes')(r)}"
        if _get("evaluation", "mouse_model", "strokes")(r) else None)),
    ("detectors", "rebrowser leaks", lambda r: (
        ", ".join(_get("evaluation", "rebrowser", "detected")(r)) or "none"
        if _get("evaluation", "rebrowser", "detected")(r) is not None else None)),
    ("detectors", "creepjs headless %", _get("evaluation", "creepjs", "headless")),
    ("detectors", "creepjs stealth %", _get("evaluation", "creepjs", "stealth")),
    ("detectors", "creepjs lies", _get("evaluation", "creepjs", "lie_count")),
] + [("input", key, _get("stats", key)) for key in (
    "duration_s", "mouse_moves", "moves_per_s", "untrusted_moves", "strokes",
    "stroke_straightness", "stroke_speed_px_ms", "stroke_peak_speed_px_ms", "stroke_speed_cv",
    "stroke_turn_rad", "stroke_end_speed_ratio", "clicks", "click_hold_ms", "click_hold_cv",
    "wheel_events", "wheel_gap_ms", "wheel_gap_cv", "scroll_px", "reading_pauses",
    "keys", "key_hold_ms", "key_gap_cv",
)]


def compare(run_ids: list[str]) -> dict:
    """The chosen runs side by side: the lab's verdicts, every lab check, the
    independent judges, and the raw input measurements."""
    runs = [r for r in (get_run(i) for i in run_ids) if r]
    columns = [{
        "id": r["id"], "scenario": r.get("scenario"), "style": r.get("style", "human"),
        "identity": r.get("identity"), "started_at": r.get("started_at"), "status": r.get("status"),
    } for r in runs]
    rows = [{"section": section, "label": label, "values": [getter(r) for r in runs]}
            for section, label, getter in _COMPARE_ROWS]

    # Each lab check by name, in the order the lab lists them.
    names: list[tuple[str, str]] = []
    for r in runs:
        for c in (r.get("score") or {}).get("checks", []):
            key = (c.get("group", "?"), c.get("name", "?"))
            if key not in names:
                names.append(key)
    for group, name in names:
        values = []
        for r in runs:
            match = next((c for c in (r.get("score") or {}).get("checks", [])
                          if (c.get("group", "?"), c.get("name")) == (group, name)), None)
            values.append(f"{match['state']}: {match['detail']}" if match else None)
        rows.append({"section": "lab check (" + ("behaviour" if group == "beh" else "fingerprint") + ")",
                     "label": name, "values": values})
    return {"runs": columns, "rows": rows}
