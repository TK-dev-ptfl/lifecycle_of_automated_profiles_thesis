"""Validates the feed lab's behaviour checks against recorded humans and bots.

    cd backend
    .venv/Scripts/python.exe -I tests/behaviour/test_env/validate_lab_checks.py

A check is only a measurement of human-likeness if real people pass it and
plain automation does not. This runs the lab's own rules - ported line for line
from feed-lab/index.html, behaviourChecks() - over public recordings that were
never produced by this project:

  mouse paths   SapiMouse (120 people), Iliou et al. humans, against Iliou
                moderate and advanced bots and BeCAPTCHA-style synthetic paths
  click holds   SapiMouse press/release pairs
  keystrokes    CMU keystroke benchmark (51 typists, Killourhy & Maxion 2009)

Datasets live in bot_model/data (gitignored; see bot_model/README.md). Writes
VALIDATION.md next to this file.

The port must stay in step with index.html. Each function names the lines it
mirrors; if you change a threshold in the lab, change it here and re-run.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import random
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))  # backend/, for the shared loaders

from tests.behaviour.test_env.bot_model import train as bot_model  # noqa: E402

DATA = HERE / "bot_model" / "data"
OUT = HERE / "VALIDATION.md"
rng = random.Random(11)


# --- the lab's rules, ported from feed-lab/index.html ------------------------------

def _mean(a):
    return sum(a) / len(a)


def _cv(a):
    # index.html: cv = sd / mean, population sd, NaN below two values
    if len(a) < 2:
        return float("nan")
    m = _mean(a)
    return math.sqrt(_mean([(x - m) ** 2 for x in a])) / m if m else float("nan")


def _median(a):
    s = sorted(a)
    if not s:
        return float("nan")
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def lab_strokes(moves):
    """index.html strokes(): cut at gaps > 150 ms, keep >= 6 points spanning >= 80 px."""
    groups, cur = [], []
    for p in moves:
        if cur and p[0] - cur[-1][0] > 150:
            groups.append(cur)
            cur = []
        cur.append(p)
    if cur:
        groups.append(cur)
    out = []
    for s in groups:
        if len(s) < 6:
            continue
        d = math.dist(s[0][1:], s[-1][1:])
        if d < 80:
            continue
        path, peak, speeds, angs = 0.0, 0.0, [], []
        for a, b in zip(s, s[1:]):
            seg = math.dist(a[1:], b[1:])
            path += seg
            if seg > 0:
                v = seg / max(b[0] - a[0], 4)
                speeds.append(v)
                peak = max(peak, v)
                angs.append(math.atan2(b[2] - a[2], b[1] - a[1]))
        turns = []
        for a1, a2 in zip(angs, angs[1:]):
            t = a2 - a1
            while t > math.pi:
                t -= 2 * math.pi
            while t < -math.pi:
                t += 2 * math.pi
            turns.append(abs(t))
        out.append({"straight": d / path, "speedCV": _cv(speeds),
                    "turn": _mean(turns) if turns else 0.0, "peak": peak})
    return out


def mouse_checks(moves):
    """index.html behaviourChecks(), the four stroke checks. None = pending."""
    st = lab_strokes(moves)
    if len(st) < 4:
        return None
    fs = sum(1 for s in st if s["straight"] > .995) / len(st)
    scv = _median([s["speedCV"] for s in st if math.isfinite(s["speedCV"])])
    turn = _median([s["turn"] for s in st])
    peak = max(s["peak"] for s in st)
    return {
        "Curved, imperfect paths": "fail" if fs > .5 else "warn" if fs > .25 else "pass",
        "Speed rises and falls": "fail" if scv < .15 else "warn" if scv < .3 else "pass",
        "Small direction jitter": "fail" if turn < .005 else "warn" if turn < .02 else "pass",
        "Plausible top speed": "fail" if peak > 40 else "warn" if peak > 20 else "pass",
    }


def press_check(holds):
    """index.html 'Natural press length': >= 4 presses, median < 20 ms fails,
    variation < 0.08 over >= 5 presses warns."""
    if len(holds) < 4:
        return None
    m, c = _median(holds), _cv(holds)
    return "fail" if m < 20 else "warn" if (c < .08 and len(holds) >= 5) else "pass"


def keystroke_check(holds, flights):
    """index.html 'Keystroke rhythm': >= 10 holds; flights are keydown-to-keydown
    gaps under 1.5 s."""
    if len(holds) < 10:
        return None
    flights = [f for f in flights if f < 1500]
    m, c = _median(holds), _cv(flights)
    return "fail" if (m < 10 or c < .12) else "warn" if (m < 25 or c < .2) else "pass"


# --- data -----------------------------------------------------------------------

def sapimouse_sessions():
    """(moves incl. drags, click holds) per session file. A press is a click when
    no drag happens before its release."""
    out = []
    for path in sorted(glob.glob(str(DATA / "sapimouse" / "sapimouse" / "user*" / "*.csv"))):
        moves, holds, down, dragged = [], [], None, False
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                t, state = float(row["client timestamp"]), row["state"]
                if state in ("Move", "Drag"):
                    moves.append((t, float(row["x"]), float(row["y"])))
                    dragged |= state == "Drag" and down is not None
                elif state == "Pressed":
                    down, dragged = t, False
                elif state == "Released" and down is not None:
                    if not dragged:
                        holds.append(t - down)
                    down = None
        out.append((moves, holds))
    return out


def cmu_reps():
    """(holds, flights) in ms per typed password - about one short comment's
    worth of keys, the size of sample the lab sees."""
    reps = []
    with open(DATA / "cmu_keystroke" / "DSL-StrongPasswordData.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            holds = [float(v) * 1000 for k, v in row.items() if k.startswith("H.")]
            flights = [float(v) * 1000 for k, v in row.items() if k.startswith("DD.")]
            reps.append((holds, flights))
    return reps


def naive_keystrokes(n=200):
    """What Playwright's keyboard.type(text, delay=40) produces: one fixed gap,
    keys released as soon as they go down. A sanity row, not a dataset."""
    return [([rng.uniform(0.5, 2.5) for _ in range(30)], [40.0 + rng.uniform(-1, 1) for _ in range(29)])
            for _ in range(n)]


# --- tallying ---------------------------------------------------------------------

def tally(results):
    """results: list of dict(check -> state) or None (pending)."""
    judged = [r for r in results if r is not None]
    per = {}
    for r in judged:
        for check, state in r.items():
            per.setdefault(check, Counter())[state] += 1
    return len(results), len(judged), per


def pct(c: Counter, state: str) -> str:
    n = sum(c.values())
    return f"{100 * c[state] / n:.1f}%" if n else "–"


def main() -> int:
    needed = [DATA / "sapimouse", DATA / "iliou", DATA / "cmu_keystroke" / "DSL-StrongPasswordData.csv"]
    missing = [str(p) for p in needed if not p.exists()]
    if missing:
        print("missing datasets (see bot_model/README.md):\n  " + "\n  ".join(missing))
        return 2

    print("loading...")
    sapi = sapimouse_sessions()
    iliou = bot_model.load_iliou()
    by_label = {}
    for label, _phase, _split, moves in iliou.values():
        by_label.setdefault(label, []).append(moves)

    # Synthetic paths after BeCAPTCHA-Mouse Method 1, on SapiMouse's own strokes
    # (same endpoints and timestamps), so only the shape and velocity profile differ.
    synthetic = []
    for moves, _ in sapi[:120]:
        session = []
        for s in bot_model.strokes(moves):
            session.extend(bot_model.synthetic_like(s))
        synthetic.append(session)

    mouse_sets = [
        ("Human: SapiMouse", [m for m, _ in sapi]),
        ("Human: Iliou et al.", by_label.get("human", [])),
        ("Bot: Iliou moderate", by_label.get("moderate_bot", [])),
        ("Bot: Iliou advanced", by_label.get("advanced_bot", [])),
        ("Bot: synthetic (BeCAPTCHA Method 1)", synthetic),
    ]
    mouse_rows = []
    for name, sessions in mouse_sets:
        total, judged, per = tally([mouse_checks(s) for s in sessions])
        mouse_rows.append((name, total, judged, per))
        print(f"  {name}: {judged}/{total} sessions judged")

    press_results = [press_check(h) for _, h in sapi]
    press_judged = [r for r in press_results if r]
    all_holds = [h for _, hs in sapi for h in hs]

    cmu = cmu_reps()
    key_rows = [
        ("Human: CMU benchmark", [keystroke_check(h, f) for h, f in cmu]),
        ("Bot: Playwright type(delay=40)", [keystroke_check(h, f) for h, f in naive_keystrokes()]),
    ]

    checks = ["Curved, imperfect paths", "Speed rises and falls", "Small direction jitter", "Plausible top speed"]
    lines = [
        "# Feed lab checks against recorded humans and bots", "",
        f"Generated by `validate_lab_checks.py` on {date.today().isoformat()}. The lab's own rules "
        "(feed-lab/index.html, `behaviourChecks()`), ported to Python and run on public recordings "
        "this project did not produce. A check works as a measure of human-likeness when the "
        "**fail** rate is low on humans and high on bots.", "",
        "A session is *judged* when it has enough input for the check (the lab shows *Waiting* otherwise).", "",
        "## Mouse paths", "",
    ]
    for check in checks:
        lines += [f"### {check}", "", "| Data | Sessions judged | Pass | Warn | Fail |", "|---|---|---|---|---|"]
        for name, total, judged, per in mouse_rows:
            c = per.get(check, Counter())
            lines.append(f"| {name} | {judged}/{total} | {pct(c, 'pass')} | {pct(c, 'warn')} | {pct(c, 'fail')} |")
        lines.append("")

    # Session-level: does a session fail at least one of the four checks?
    lines += ["### Any of the four failing", "", "| Data | Sessions judged | At least one fail |", "|---|---|---|"]
    for name, sessions in mouse_sets:
        res = [r for r in (mouse_checks(s) for s in sessions) if r]
        anyfail = sum(1 for r in res if "fail" in r.values())
        lines.append(f"| {name} | {len(res)} | {100 * anyfail / max(len(res), 1):.1f}% |")
    lines.append("")

    pc = Counter(press_judged)
    lines += [
        "## Click press length", "",
        f"SapiMouse, {len(all_holds)} clicks (presses released without a drag): median "
        f"{_median(all_holds):.0f} ms, 5th-95th percentile "
        f"{sorted(all_holds)[int(.05 * len(all_holds))]:.0f}-{sorted(all_holds)[int(.95 * len(all_holds))]:.0f} ms.", "",
        "| Data | Sessions judged | Pass | Warn | Fail |", "|---|---|---|---|---|",
        f"| Human: SapiMouse | {len(press_judged)}/{len(press_results)} | {pct(pc, 'pass')} | {pct(pc, 'warn')} | {pct(pc, 'fail')} |",
        "",
        "## Keystroke rhythm", "",
        "One CMU repetition is one typed password: 11 holds and 10 keydown-to-keydown gaps, about "
        "the size of a short comment.", "",
        "| Data | Samples judged | Pass | Warn | Fail |", "|---|---|---|---|---|",
    ]
    for name, res in key_rows:
        judged = [r for r in res if r]
        c = Counter(judged)
        lines.append(f"| {name} | {len(judged)}/{len(res)} | {pct(c, 'pass')} | {pct(c, 'warn')} | {pct(c, 'fail')} |")
    lines += [
        "",
        "## Not validated here", "",
        "- **Event provenance** (`isTrusted`, pointer events, click under the cursor, hover before click, "
        "text through keys, scrolling follows input, screen/client offsets, movement deltas, coalesced "
        "samples) are browser facts, not statistics: they follow from the DOM and Pointer Events "
        "specifications and from how CDP injects input. There is no recorded data to tune them on.",
        "- **Time before first action, imprecise aim, pauses to read, uneven wheel timing** have no "
        "matching public dataset here. Their thresholds are heuristics; treat them as weaker evidence.",
        "",
        "## Caveats", "",
        "- CMU typists typed one fixed password 400 times, so their rhythm is *more* regular than free "
        "text. A check that passes them is conservative for comments.",
        "- SapiMouse is a drag-and-drop task recorded by a desktop app, Iliou a web page; the lab is a feed. "
        "Path statistics transfer between tasks only approximately.",
        "- The synthetic bot row uses real human timestamps, so it isolates path shape and velocity profile.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
