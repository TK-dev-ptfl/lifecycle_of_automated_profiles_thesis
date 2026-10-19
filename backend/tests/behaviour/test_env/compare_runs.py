"""Prints saved behaviour runs side by side.

    cd backend
    PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/compare_runs.py
    PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/compare_runs.py RUN_ID RUN_ID ...
    ... --csv out.csv     also write the table as CSV, for the thesis
    ... --aggregate       every finished run, grouped by scenario, with tests

With no ids it takes the latest finished run of each scenario - typically the
manual (human) session, the behaviour algorithm and the robotic control - so
the comparison the dashboard shows is one command away in a terminal too.
Runs are read from tests/behaviour/test_env/runs/*/run.json.

--aggregate is the one to report. A single run per condition is an anecdote:
it summarises all of them per scenario (median and interquartile range) and
tests whether each style differs from the manual human baseline on the
classifier's bot probability (Mann-Whitney U, with AUC as the effect size:
0.5 = indistinguishable from the human sessions, 1.0 = always more bot-like).
Every saved trace is re-scored with the current classifier, so runs recorded
before a retrain are judged by the same model as the rest. Only runs of the
current PROTOCOL are pooled; after changing the algorithm, pass --since with
the time of the change so old and new behaviour are not mixed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path

from app.behaviour.evaluation import mouse_model
from app.services import behaviour_run_service

WIDTH = 30
BASELINE = "feed-lab-manual"
# What --aggregate summarises: (label, getter on a run dict).
AGGREGATE_METRICS = [
    ("classifier bot probability", lambda r: r.get("_bot_probability")),
    ("lab behaviour score", lambda r: _num((r.get("score") or {}).get("behaviour", {}).get("value"))),
    ("lab behaviour bot signals", lambda r: sum(
        1 for c in (r.get("score") or {}).get("checks", []) if c.get("group") == "beh" and c.get("state") == "fail")),
    ("reCAPTCHA v3", lambda r: _num((r.get("score") or {}).get("recaptcha", {}).get("value"))),
] + [(key, (lambda k: lambda r: (r.get("stats") or {}).get(k))(key)) for key in (
    "stroke_straightness", "stroke_speed_cv", "stroke_end_speed_ratio", "click_hold_ms",
    "key_hold_ms", "key_gap_cv", "wheel_gap_cv", "reading_pauses",
)]


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mann_whitney(a: list[float], b: list[float]) -> tuple[float, float]:
    """(AUC, two-sided p) for "b is larger than a".

    AUC = U / (n_a * n_b), the probability that a random b exceeds a random a
    (Hanley & McNeil 1982). p from the normal approximation with tie
    correction, which is rough below about 8 per group - report n with it.
    """
    pooled = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = [0.0] * len(pooled), 0
    ties = 0.0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    na, nb = len(a), len(b)
    r_b = sum(r for r, (_, group) in zip(ranks, pooled) if group == 1)
    u = r_b - nb * (nb + 1) / 2
    n = na + nb
    var = na * nb / 12 * ((n + 1) - ties / (n * (n - 1))) if n > 1 else 0
    z = (u - na * nb / 2) / math.sqrt(var) if var > 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return u / (na * nb), p


def _quartiles(values: list[float]) -> str:
    if len(values) == 1:
        return f"{values[0]:.3g}"
    q1, q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return f"{q2:.3g} [{q1:.3g}-{q3:.3g}]"


def rescore(run: dict) -> dict:
    """The run with _bot_probability from the current classifier, read from
    its saved trace when there is one."""
    trace_path = Path(behaviour_run_service.RUNS_DIR) / run["id"] / "trace.json"
    probability = (run.get("evaluation") or {}).get("mouse_model", {}).get("bot_probability")
    if trace_path.exists() and mouse_model.model_available():
        scored = mouse_model.score_trace(json.loads(trace_path.read_text(encoding="utf-8")))
        if scored.get("strokes", 0) >= mouse_model.MIN_STROKES:
            probability = scored.get("bot_probability")
        else:
            probability = None
    return {**run, "_bot_probability": probability}


def aggregate(runs: list[dict]) -> dict:
    """{"groups": {scenario: n}, "rows": [(metric, {scenario: summary})],
    "tests": [(scenario, n_base, n, auc, p)]}"""
    groups: dict[str, list[dict]] = {}
    for run in runs:
        groups.setdefault(run.get("scenario", "?"), []).append(run)
    rows = []
    for label, get in AGGREGATE_METRICS:
        cells = {}
        for scenario, members in groups.items():
            values = [v for v in (get(r) for r in members) if isinstance(v, (int, float))]
            cells[scenario] = f"{_quartiles(values)} (n={len(values)})" if values else "-"
        rows.append((label, cells))
    tests = []
    base = [r["_bot_probability"] for r in groups.get(BASELINE, []) if r.get("_bot_probability") is not None]
    for scenario, members in groups.items():
        if scenario == BASELINE:
            continue
        other = [r["_bot_probability"] for r in members if r.get("_bot_probability") is not None]
        if base and other:
            auc, p = mann_whitney(base, other)
            tests.append((scenario, len(base), len(other), auc, p))
    return {"groups": {k: len(v) for k, v in groups.items()}, "rows": rows, "tests": tests}


def print_aggregate(csv_path=None, since: str = "") -> int:
    runs = [rescore(r) for r in behaviour_run_service.list_runs(limit=10_000)
            if r.get("status") == "completed"
            and r.get("protocol", 1) == behaviour_run_service.PROTOCOL
            and r.get("started_at", "") >= since]
    if not runs:
        print(f"no finished protocol-{behaviour_run_service.PROTOCOL} runs"
              + (f" since {since}" if since else "") + " yet")
        return 1
    print(f"protocol {behaviour_run_service.PROTOCOL} runs" + (f" since {since}" if since else "") + "\n")
    result = aggregate(runs)
    order = sorted(result["groups"], key=lambda k: (k != BASELINE, k))
    print(f"{'':<30}" + "".join(f"{cell(f'{k} ({result['groups'][k]} runs)'):<{WIDTH + 2}}" for k in order))
    for label, cells in result["rows"]:
        print(f"  {cell(label):<28}" + "".join(f"{cell(cells.get(k, '-')):<{WIDTH + 2}}" for k in order))
    print("\nmedian [interquartile range]; classifier probabilities re-scored with the current model")
    if not result["tests"]:
        print(f"\nno test: needs finished runs of {BASELINE} (the human baseline) and of another scenario")
    for scenario, nb, n, auc, p in result["tests"]:
        print(f"\n{scenario} vs {BASELINE}: AUC {auc:.2f} (0.5 = like the human sessions), "
              f"Mann-Whitney p = {p:.3g}, n = {nb} vs {n}"
              + ("  - too few runs for p to mean much" if min(nb, n) < 5 else ""))
    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["metric", *order])
            writer.writerow(["runs", *[result["groups"][k] for k in order]])
            for label, cells in result["rows"]:
                writer.writerow([label, *[cells.get(k, "") for k in order]])
            for scenario, nb, n, auc, p in result["tests"]:
                writer.writerow([f"AUC vs {BASELINE}: {scenario}", auc, f"p={p:.3g}", f"n={nb} vs {n}"])
        print(f"\nwrote {csv_path}")
    return 0


def latest_per_scenario() -> list[str]:
    chosen: dict[str, str] = {}
    for run in behaviour_run_service.list_runs(limit=500):
        if run.get("status") == "completed" and run.get("scenario") not in chosen:
            chosen[run["scenario"]] = run["id"]
    order = ["feed-lab-manual", "feed-lab", "feed-lab-bot"]
    return [chosen[k] for k in sorted(chosen, key=lambda k: order.index(k) if k in order else 99)]


def cell(value) -> str:
    text = "-" if value is None else str(value)
    return text if len(text) <= WIDTH else text[: WIDTH - 1] + "…"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--aggregate", action="store_true",
                    help="all finished runs per scenario, with a test against the manual baseline")
    ap.add_argument("--since", default="",
                    help="--aggregate only: runs started at or after this ISO time, e.g. after an algorithm change")
    args = ap.parse_args()
    if args.aggregate:
        return print_aggregate(args.csv, args.since)

    ids = args.ids or latest_per_scenario()
    if not ids:
        print("no saved runs yet - run the feed lab scenarios first")
        return 1
    table = behaviour_run_service.compare(ids)
    if not table["runs"]:
        print("none of those run ids were found")
        return 1

    heads = [f"{r['style']}: {r['scenario']}" for r in table["runs"]]
    print(f"{'':<36}" + "".join(f"{cell(h):<{WIDTH + 2}}" for h in heads))
    print(f"{'':<36}" + "".join(f"{cell(r['id'][:8] + ' ' + (r['started_at'] or '')[:16]):<{WIDTH + 2}}" for r in table["runs"]))
    section = None
    for row in table["rows"]:
        if row["section"] != section:
            section = row["section"]
            print(f"\n[{section}]")
        print(f"  {cell(row['label']):<34}" + "".join(f"{cell(v):<{WIDTH + 2}}" for v in row["values"]))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["section", "metric", *heads])
            writer.writerow(["", "run id", *[r["id"] for r in table["runs"]]])
            for row in table["rows"]:
                writer.writerow([row["section"], row["label"], *["" if v is None else v for v in row["values"]]])
        print(f"\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
