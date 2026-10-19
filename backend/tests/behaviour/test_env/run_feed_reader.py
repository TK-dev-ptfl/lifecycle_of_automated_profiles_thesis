"""Drives the feed lab with app.behaviour from the command line.

    # terminal 1
    cd backend/tests/behaviour/test_env/feed-lab && node server.mjs

    # terminal 2
    cd backend
    PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/run_feed_reader.py

Flags: --headless, --show-cursor, --no-proxy, --no-evaluate, --public-checks, --manual-minutes M, --want N, --identity NAME, --url URL, --scenario KEY

The same thing the dashboard's Algorithm page runs, and deliberately the same
code: the scenario (where the posts are and what to read from each) lives in
app.services.behaviour_run_service, so the CLI and the UI can never drift into
testing different things. This file is just a terminal front end for it.
"""
from __future__ import annotations

import argparse
import asyncio

from app.services import behaviour_run_service


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="feed-lab")
    ap.add_argument("--url", default=None, help="override the scenario's URL")
    ap.add_argument("--want", type=int, default=8)
    ap.add_argument("--identity", default="feed-reader-1")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--show-cursor", action="store_true",
                    help="draw the simulated pointer (debug only; the page can see it)")
    ap.add_argument("--no-proxy", action="store_true",
                    help="go out on this machine's own address instead of a proxy from the list")
    ap.add_argument("--no-evaluate", action="store_true",
                    help="skip the mouse classifier and the rebrowser/CreepJS detectors")
    ap.add_argument("--manual-minutes", type=float, default=10.0,
                    help="feed-lab-manual only: end the session after this long if Finish is not clicked")
    ap.add_argument("--public-checks", action="store_true",
                    help="also visit public detector pages (sannysoft, BrowserScan, ...); proxy only")
    args = ap.parse_args()

    if args.scenario not in behaviour_run_service.SCENARIOS:
        print(f"unknown scenario; known: {', '.join(behaviour_run_service.SCENARIOS)}")
        return 2

    run = behaviour_run_service.start_run(
        args.scenario,
        identity=args.identity,
        want=args.want,
        headless=args.headless,
        show_cursor=args.show_cursor,
        use_proxy=not args.no_proxy,
        evaluate=not args.no_evaluate,
        public_checks=args.public_checks,
        manual_minutes=args.manual_minutes,
        url=args.url,
    )

    # Mirror the log to the terminal as it happens, rather than waiting for the
    # run to end - a browsing run takes tens of seconds and silence looks broken.
    shown = 0
    # Until finished_at, not until status changes: status flips to completed
    # before the browser has closed, and returning then leaves it orphaned.
    while run.finished_at is None:
        while shown < len(run.logs):
            print(f"  {run.logs[shown]}")
            shown += 1
        await asyncio.sleep(0.2)
    while shown < len(run.logs):
        print(f"  {run.logs[shown]}")
        shown += 1

    if run.status == "failed":
        print(f"\nFAILED: {run.error}")
        return 1

    if run.proxy:
        print("\n--- through ---")
        for key, value in run.proxy.items():
            print(f"  {key:<10} {value}")

    if run.fingerprint:
        print("\n--- presented as ---")
        for key, value in run.fingerprint.items():
            print(f"  {key:<10} {value}")

    print(f"\n--- read {len(run.items)} posts in {run.elapsed_s:.0f}s ---")
    for i, post in enumerate(run.items, 1):
        body = post.get("body", "").replace("\n", " ")
        print(f"  {i}. {post.get('author')} {post.get('handle')}")
        print(f"     {body[:88]}{'…' if len(body) > 88 else ''}")
        print(
            f"     {post.get('likes')} likes · {post.get('comments')} comments "
            f"· {post.get('reposts')} reposts"
        )

    score = run.score or {}
    if score:
        print("\n--- what the page made of it ---")
        print(f"  overall     {score.get('overall')}  ({score.get('verdict')})")
        for name in ("behaviour", "fingerprint", "recaptcha"):
            row = score.get(name) or {}
            print(f"  {name:<11} {str(row.get('value', '–')):<6} {row.get('detail', '')}")
        bad = [c for c in score.get("checks", []) if c.get("state") in ("fail", "warn")]
        if bad:
            print("\n  checks not passing:")
            for c in bad:
                print(f"    [{c['state']}] ({c.get('group', '?')}) {c['name']}: {c['detail']}")

    ev = run.evaluation or {}
    if ev:
        print("\n--- independent judges ---")
        m = ev.get("mouse_model") or {}
        if m:
            extra = f" (bot probability {m['bot_probability']}, {m.get('bot_like_strokes')}/{m['strokes']} strokes bot-like)" if "bot_probability" in m else ""
            print(f"  mouse classifier  {m.get('verdict')}{extra}")
        rb = ev.get("rebrowser") or {}
        if "checks" in rb:
            print(f"  rebrowser         {len(rb['detected'])} leak(s) detected")
            for c in rb["checks"]:
                if c["state"] != "pass":
                    print(f"    [{c['state']}] {c['name']}: {c['detail'][:110]}")
        elif rb:
            print(f"  rebrowser         {rb.get('error')}")
        cj = ev.get("creepjs") or {}
        if "headless" in cj:
            print(f"  creepjs           headless {cj['headless']}%, like headless {cj['like_headless']}%, "
                  f"stealth {cj['stealth']}%, {cj['lie_count']} lie(s), worker lied: {cj['worker_lied']}")
            flags = cj["headless_flags"] + cj["stealth_flags"]
            if flags:
                print(f"    flags: {', '.join(flags)}")
            for api, why in list(cj["lies"].items())[:8]:
                print(f"    lie: {api} - {', '.join(why) if isinstance(why, list) else why}")
        elif cj:
            print(f"  creepjs           {cj.get('error')}")
        for page in ev.get("public") or []:
            if "error" in page:
                print(f"  {page.get('name', 'public'):<17} {page['error']}")
            elif "passed" in page:
                print(f"  {page['name']:<17} {page['passed']} passed, failed: {page['failed'] or 'none'}, warn: {page['warned'] or 'none'}")
            else:
                print(f"  {page['name']:<17} see screenshot; " + " | ".join(page.get("highlights", [])[:3])[:150])
        if run.artifacts_dir:
            print(f"\n  screenshots and trace: {run.artifacts_dir}")

    return 0 if run.items or run.style == "manual" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
