"""Drives the feed lab with app.behaviour from the command line.

    # terminal 1
    cd backend/tests/behaviour/test_env/feed-lab && node server.mjs

    # terminal 2
    cd backend
    PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/run_feed_reader.py

Flags: --headless, --show-cursor, --want N, --identity NAME, --url URL, --scenario KEY

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

    return 0 if run.items else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
