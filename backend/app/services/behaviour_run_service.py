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
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.behaviour.adapters.playwright_env import PlaywrightEnvironment
from app.behaviour.environment import Target
from app.behaviour.executor import Actor
from app.behaviour.fingerprint import (
    fingerprint_for,
    launch as launch_fingerprinted,
    new_context as fingerprinted_context,
    read_real_browser,
)
from app.behaviour.goals import ClickOn, Dwell, FeedSchema, ReadFeed, Wander
from app.behaviour.profile import derive_for

MAX_LOG_LINES = 400
# A browsing run is minutes at most; past this something is wedged and the
# browser needs closing rather than leaving on the host indefinitely.
RUN_TIMEOUT_S = 600


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
        schema=FeedSchema(
            item=Target("article.post", "feed posts"),
            fields={
                "author": ".who-line b",
                "handle": ".who-line span",
                "body": "p.text",
                "likes": ".act.like span",
                "comments": ".act.cmt-btn span",
                "reposts": ".act.rep span",
            },
        ),
        score_js=FEED_LAB_SCORE_JS,
    ),
}


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
    status: str = "running"          # running | completed | failed
    profile: dict = field(default_factory=dict)
    # The machine and browser the identity presented (behaviour.fingerprint).
    fingerprint: dict = field(default_factory=dict)
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
            "show_cursor": self.show_cursor,
            "status": self.status, "profile": self.profile,
            "fingerprint": self.fingerprint, "logs": self.logs,
            "items": self.items, "score": self.score, "error": self.error,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "elapsed_s": round(self.elapsed_s, 1),
        }


_runs: dict[str, BehaviourRun] = {}


def list_scenarios() -> list[dict]:
    return [
        {"key": s.key, "name": s.name, "description": s.description, "url": s.url,
         "fields": list(s.schema.fields)}
        for s in SCENARIOS.values()
    ]


def get_run(run_id: str) -> Optional[dict]:
    run = _runs.get(run_id)
    return run.as_dict() if run else None


def list_runs(limit: int = 10) -> list[dict]:
    newest = sorted(_runs.values(), key=lambda r: r.started_at, reverse=True)
    return [r.as_dict() for r in newest[:limit]]


def start_run(
    scenario_key: str,
    *,
    identity: str,
    want: int,
    headless: bool,
    url: Optional[str] = None,
    show_cursor: bool = False,
) -> BehaviourRun:
    """Creates the run record and schedules it. Returns immediately - the browser
    takes tens of seconds, which no HTTP request should wait on."""
    scenario = SCENARIOS[scenario_key]
    run = BehaviourRun(
        id=str(uuid.uuid4()),
        scenario=scenario.key,
        identity=identity,
        url=url or scenario.url,
        want=want,
        headless=headless,
        show_cursor=show_cursor,
    )
    _runs[run.id] = run
    asyncio.create_task(_execute(run, scenario), name=f"behaviour-run:{run.id}")
    return run


async def _execute(run: BehaviourRun, scenario: Scenario) -> None:
    try:
        await asyncio.wait_for(_drive(run, scenario), timeout=RUN_TIMEOUT_S)
    except asyncio.TimeoutError:
        run.status = "failed"
        run.error = f"run exceeded {RUN_TIMEOUT_S}s and was stopped"
        run.log(run.error)
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.log(run.error)
        print(f"[behaviour-run {run.id}] failed:\n{traceback.format_exc()}")
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()


async def _drive(run: BehaviourRun, scenario: Scenario) -> None:
    # Imported here rather than at module import: the backend should start fine
    # on a machine where Playwright's browsers were never installed, and only
    # fail when someone actually asks for a run.
    from playwright.async_api import async_playwright

    profile = derive_for(run.identity)
    run.profile = {
        "typing_wpm": round(profile.typing_wpm),
        "hesitancy": round(profile.hesitancy, 2),
        "aim_scatter": round(profile.aim_scatter, 2),
        "path_curviness": round(profile.path_curviness, 2),
        "restlessness": round(profile.restlessness, 2),
        "reads_with_cursor": round(profile.reads_with_cursor, 2),
        "patience_s": round(profile.patience_s),
        "wander_range": list(profile.wander_range),
    }
    run.log(f"persona {run.identity}: {run.profile}")

    async with async_playwright() as pw:
        # The machine comes from the same identity key as the persona: the
        # browser it claims is the browser launched, and everything else is
        # presented through that browser's own settings. See behaviour.fingerprint.
        fp = fingerprint_for(run.identity)
        browser, fp = await launch_fingerprinted(pw, fp, headless=run.headless, log=run.log)
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
            page = await context.new_page()

            run.log(f"opening {run.url}")
            await page.goto(run.url, wait_until="domcontentloaded", timeout=30_000)
            try:
                await page.wait_for_selector(scenario.schema.item.query, timeout=15_000)
            except Exception as exc:
                raise RuntimeError(
                    f"no {scenario.schema.item} on {run.url} - is the target running?"
                ) from exc

            env = PlaywrightEnvironment(page)
            actor = Actor(env=env, profile=profile, log=run.log)

            await actor.pursue([
                Dwell(reason="taking in the page"),
                Wander(reason="settling in before reading"),
                ReadFeed(scenario.schema, want=run.want),
            ])
            run.items = list(actor.collected)
            run.elapsed_s = env.now()

            if scenario.score_js:
                run.score = await _read_score(page, actor, scenario.score_js)
                if run.score:
                    run.log(
                        f"page scored the session {run.score.get('overall')} "
                        f"({run.score.get('verdict')})"
                    )

            run.status = "completed"
            run.log(f"read {len(run.items)} item(s) in {run.elapsed_s:.0f}s")
        finally:
            await browser.close()


async def _read_score(page, actor: Actor, score_js: str) -> Optional[dict]:
    """Reads the page's verdict, including every check from both detail tabs.

    The tabs are opened by the same actor that did the reading, with its own
    hand: an instant programmatic click at the end would be scored too, and
    would mark the session down for the measurement itself. Each tab shows only
    its own checks, so the two lists are read one after the other and merged.
    """
    await actor.pursue([Dwell(seconds=1.2, reason="glancing at the session check")])
    checks: list[dict] = []
    score: Optional[dict] = None
    for tab, label in (("beh", "behaviour details"), ("fp", "fingerprint details")):
        try:
            await actor.pursue([ClickOn(Target(f'[data-tab="{tab}"]', label))])
            await page.wait_for_timeout(700)
        except Exception as exc:
            actor.log(f"could not open {label}: {exc}")
            continue
        score = await page.evaluate(score_js)
        for check in (score or {}).get("checks", []):
            checks.append({**check, "group": tab})
    if score is None:
        score = await page.evaluate(score_js)
    if score is not None:
        score["checks"] = checks
    return score
