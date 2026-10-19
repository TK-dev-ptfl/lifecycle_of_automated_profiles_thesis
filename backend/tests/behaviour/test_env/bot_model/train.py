"""Trains the behaviour classifier that scores runs (app.behaviour.evaluation).

    cd backend
    .venv/Scripts/python.exe -m pip install -r requirements-eval.txt
    PYTHONPATH=. .venv/Scripts/python.exe tests/behaviour/test_env/bot_model/train.py

Data (downloaded into ./data, which is gitignored - see README.md here):

  humans   SapiMouse (Sapientia University, 120 users), and the human sessions of
           the Iliou et al. Web Bot Detection Dataset (CC BY-NC-SA 2.0)
  bots     the moderate and advanced bot sessions of the same Iliou dataset, and
           function-based synthetic trajectories re-implemented from
           BeCAPTCHA-Mouse Method 1 (Acien et al., Pattern Recognition 2022) -
           the benchmark itself is licence-restricted, its method is published

Held out entirely, for the numbers in REPORT.md:
  - Iliou phase 1 "test" split, exactly as its authors published it
  - SapiMouse users 101-120, against synthetic strokes built on their endpoints

Writes app/behaviour/evaluation/mouse_model.json and REPORT.md next to this file.
Never trained on, and never should be: anything app.behaviour or the robotic
control produced. The classifier is only an independent judge if it has not
seen the thing it is judging.
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from app.behaviour.evaluation.mouse_features import FEATURE_NAMES, features, strokes

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT_MODEL = HERE.parents[3] / "app" / "behaviour" / "evaluation" / "mouse_model.json"
OUT_REPORT = HERE / "REPORT.md"

SEED = 7
MAX_STROKES_PER_SESSION = 200
SAPI_HELD_OUT_USERS = set(range(101, 121))
NUM = re.compile(r"-?\d+(?:\.\d+)?")

rng = random.Random(SEED)


# --- loading ---------------------------------------------------------------

def load_sapimouse():
    """(user, moves) per session file. Moves only - SapiMouse also logs drags
    and presses, which are not free pointer motion."""
    sessions = []
    for path in sorted(glob.glob(str(DATA / "sapimouse" / "sapimouse" / "user*" / "*.csv"))):
        user = int(Path(path).parent.name.removeprefix("user"))
        moves = []
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("state") == "Move":
                    moves.append((float(row["client timestamp"]), float(row["x"]), float(row["y"])))
        sessions.append((user, Path(path).stem, moves))
    return sessions


def _iliou_moves(record: dict):
    times = [float(t) for t in NUM.findall(record.get("mousemove_times", ""))]
    coords = [float(v) for v in NUM.findall(record.get("mousemove_total_behaviour", ""))]
    points = list(zip(coords[0::2], coords[1::2]))
    n = min(len(times), len(points))
    return [(times[i], points[i][0], points[i][1]) for i in range(n)]


def load_iliou():
    """{session_id: (label, phase, split, moves)}. Phase 1 keeps its published
    train/test split; phase 2 is all training data."""
    base = DATA / "iliou"
    labels: dict[str, tuple[str, str, str]] = {}
    for split in ("train", "test"):
        for ann in glob.glob(str(base / "phase1" / "annotations" / "*" / split)):
            for line in open(ann, encoding="utf-8"):
                parts = line.split()
                if len(parts) == 2:
                    labels[parts[0]] = (parts[1], "phase1", split)
    sessions = {}
    for path in glob.glob(str(base / "phase1" / "data" / "mouse_movements" / "*" / "*" / "mouse_movements.json")):
        record = json.load(open(path, encoding="utf-8"))
        sid = record.get("session_id") or Path(path).parent.name
        if sid in labels:
            label, phase, split = labels[sid]
            sessions[sid] = (label, phase, split, _iliou_moves(record))
    files = {
        "human": base / "phase2" / "data" / "mouse_movements" / "humans" / "mouse_movements_humans.json",
        "moderate_bot": base / "phase2" / "data" / "mouse_movements" / "bots" / "mouse_movements_moderate_bots.json",
        "advanced_bot": base / "phase2" / "data" / "mouse_movements" / "bots" / "mouse_movements_advanced_bots.json",
    }
    for label, path in files.items():
        for line in open(path, encoding="utf-8"):
            if line.strip():
                record = json.loads(line)
                sessions["p2:" + record["session_id"]] = (label, "phase2", "train", _iliou_moves(record))
    return sessions


# --- synthetic bots, after BeCAPTCHA-Mouse Method 1 ----------------------------

def synthetic_like(stroke):
    """A function-based synthetic trajectory with the same endpoints, point
    count and timestamps as a real stroke.

    Re-implemented from Acien et al. (2022), Method 1: one of three shapes
    (linear, quadratic, exponential) and one of three velocity profiles
    (constant, logarithmic = accelerating, Gaussian = accelerate-decelerate),
    applied per sample. Shapes are built along the chord, so the parameter
    ranges do not depend on direction.

    The timestamps are the real stroke's own. Method 1 is about geometry and
    velocity profile, and evenly spaced synthetic timestamps would let a model
    flag these strokes on timing regularity alone - learning which generator
    made a trace instead of how it moves.
    """
    (t0, x0, y0), (t1, x1, y1) = stroke[0], stroke[-1]
    m = len(stroke)
    dx, dy = x1 - x0, y1 - y0
    span = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / span, dx / span
    shape = rng.choice(("linear", "quadratic", "exponential"))
    profile = rng.choice(("constant", "logarithmic", "gaussian"))
    a = rng.uniform(-0.35, 0.35)
    k = rng.uniform(1.0, 4.0)
    sigma = rng.uniform(0.15, 0.3)

    def progress(u: float) -> float:
        if profile == "constant":
            return u
        if profile == "logarithmic":
            return (math.exp(k * u) - 1) / (math.exp(k) - 1)
        lo = 0.5 * (1 + math.erf((0 - 0.5) / (sigma * math.sqrt(2))))
        hi = 0.5 * (1 + math.erf((1 - 0.5) / (sigma * math.sqrt(2))))
        return (0.5 * (1 + math.erf((u - 0.5) / (sigma * math.sqrt(2)))) - lo) / (hi - lo)

    def offset(s: float) -> float:
        if shape == "linear":
            return 0.0
        if shape == "quadratic":
            return 4 * a * span * s * (1 - s)
        return a * span * ((math.exp(k * s) - 1) / (math.exp(k) - 1) - s)

    out = []
    for i in range(m):
        s = progress(i / (m - 1))
        h = offset(s)
        out.append((stroke[i][0], round(x0 + dx * s + nx * h), round(y0 + dy * s + ny * h)))
    return out


# --- assembling ---------------------------------------------------------------

def capped(cut):
    if len(cut) > MAX_STROKES_PER_SESSION:
        cut = rng.sample(cut, MAX_STROKES_PER_SESSION)
    return cut


def build():
    """Rows of (vector, label, source, group, split). label 1 = bot."""
    rows = []
    sapi = load_sapimouse()
    for user, name, moves in sapi:
        split = "test" if user in SAPI_HELD_OUT_USERS else "train"
        cut = capped(strokes(moves))
        group = f"sapi:{user}"
        for s in cut:
            rows.append((features(s), 0, "sapimouse", group, split))
            rows.append((features(synthetic_like(s)), 1, "synthetic", group + ":syn", split))
    for sid, (label, phase, split, moves) in load_iliou().items():
        cut = capped(strokes(moves))
        for s in cut:
            rows.append((features(s), 0 if label == "human" else 1, f"iliou-{label}", f"iliou:{sid}", split))
    return rows, len(sapi)


def session_scores(probs, groups):
    by = defaultdict(list)
    for p, g in zip(probs, groups):
        by[g].append(p)
    return {g: float(np.mean(v)) for g, v in by.items()}


def evaluate(model, rows, name, want_sources):
    picked = [r for r in rows if r[4] == "test" and r[2] in want_sources]
    if not picked or len({r[1] for r in picked}) < 2:
        return None
    X = np.array([r[0] for r in picked])
    y = np.array([r[1] for r in picked])
    p = model.predict_proba(X)[:, 1]
    sess = session_scores(p, [r[3] for r in picked])
    sess_label = {r[3]: r[1] for r in picked}
    sy = np.array([sess_label[g] for g in sess])
    sp = np.array(list(sess.values()))
    return {
        "set": name,
        "strokes": int(len(y)), "sessions": int(len(sess)),
        "stroke_auc": round(float(roc_auc_score(y, p)), 3),
        "stroke_accuracy": round(float(accuracy_score(y, p >= 0.5)), 3),
        "session_auc": round(float(roc_auc_score(sy, sp)), 3),
        "session_accuracy": round(float(accuracy_score(sy, sp >= 0.5)), 3),
    }


# Features that look at raw event timing rather than the resampled path. They
# are the ones that could teach a model which recorder made a trace instead of
# how the hand moved, so the ablation below drops them and checks what is left.
RAW_TIMING = ["log_raw_rate", "raw_dt_cv", "raw_dt_tiny_frac", "raw_step_cv"]


class Subset:
    """A forest fitted on some feature columns, usable wherever the full one is."""

    def __init__(self, model, columns):
        self.model, self.columns = model, columns

    def predict_proba(self, X):
        return self.model.predict_proba(X[:, self.columns])


def parity(model, exported, rows, n=2000) -> float:
    """Largest difference between scikit-learn's probabilities and the backend's
    pure-Python walk of the exported trees, on held-out strokes. The backend
    only scores what the training measured if this is ~0."""
    from app.behaviour.evaluation.mouse_model import stroke_probability

    sample = rng.sample([r for r in rows if r[4] == "test"], min(n, len(rows)))
    X = np.array([r[0] for r in sample])
    sk = model.predict_proba(X)[:, 1]
    py = [stroke_probability(list(v), exported) for v in X]
    return float(max(abs(a - b) for a, b in zip(sk, py)))


def export(model) -> dict:
    trees = []
    for est in model.estimators_:
        t = est.tree_
        values = t.value[:, 0, :]
        bot = values[:, 1] / np.maximum(values.sum(axis=1), 1e-12)
        trees.append({
            "left": t.children_left.tolist(),
            "right": t.children_right.tolist(),
            "feature": [int(f) if f >= 0 else 0 for f in t.feature],
            # Full precision: a rounded threshold sends values that sit between
            # it and the true one down the other branch.
            "threshold": [float(v) for v in t.threshold],
            "value": [round(float(v), 4) for v in bot],
        })
    return {
        "name": "mouse-forest-v1",
        "trained": date.today().isoformat(),
        "trained_on": ["SapiMouse", "Iliou et al. Web Bot Detection Dataset", "BeCAPTCHA-Mouse Method 1 (re-implemented)"],
        "features": FEATURE_NAMES,
        "threshold": 0.5,
        "trees": trees,
    }


def main() -> int:
    if not (DATA / "sapimouse").exists() or not (DATA / "iliou").exists():
        print("datasets missing - see README.md in this folder for where to put them")
        return 2
    print("loading and featurising (a minute or two)...")
    rows, sapi_sessions = build()
    train = [r for r in rows if r[4] == "train"]
    counts = Counter((r[2], r[4]) for r in rows)
    for (source, split), n in sorted(counts.items()):
        print(f"  {source:<20} {split:<5} {n:>7} strokes")

    def fit(subset):
        return RandomForestClassifier(
            n_estimators=120, max_depth=14, min_samples_leaf=8,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
        ).fit(np.array([r[0] for r in subset]), np.array([r[1] for r in subset]))

    model = fit(train)

    # Ablation: the same forest without the raw-timing features.
    keep = [i for i, name in enumerate(FEATURE_NAMES) if name not in RAW_TIMING]
    def fit_cols(subset, cols):
        X = np.array([r[0] for r in subset])[:, cols]
        return Subset(RandomForestClassifier(
            n_estimators=120, max_depth=14, min_samples_leaf=8,
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED,
        ).fit(X, np.array([r[1] for r in subset])), cols)
    ablated = fit_cols(train, keep)

    # Cross-dataset check: a model that never saw Iliou, tested on all of it -
    # another recorder, another site, other people, real bots. If it still
    # separates them, what it learned transfers; if not, the in-dataset numbers
    # were measuring the recorder.
    no_iliou = fit([r for r in train if not r[2].startswith("iliou")])
    iliou_all = [(v, l, src, g, "test") for v, l, src, g, _ in rows if src.startswith("iliou")]
    cross = [r for r in (
        evaluate(no_iliou, iliou_all, "Cross-dataset (trained without Iliou): Iliou humans vs moderate bots", {"iliou-human", "iliou-moderate_bot"}),
        evaluate(no_iliou, iliou_all, "Cross-dataset (trained without Iliou): Iliou humans vs advanced bots", {"iliou-human", "iliou-advanced_bot"}),
    ) if r]

    results = [r for r in (
        evaluate(model, rows, "Iliou phase 1 test: humans vs moderate bots", {"iliou-human", "iliou-moderate_bot"}),
        evaluate(model, rows, "Iliou phase 1 test: humans vs advanced bots", {"iliou-human", "iliou-advanced_bot"}),
        evaluate(model, rows, "SapiMouse users 101-120 vs synthetic (BeCAPTCHA Method 1)", {"sapimouse", "synthetic"}),
    ) if r] + cross
    ablation = [r for r in (
        evaluate(ablated, rows, "Without raw timing: Iliou humans vs moderate bots", {"iliou-human", "iliou-moderate_bot"}),
        evaluate(ablated, rows, "Without raw timing: Iliou humans vs advanced bots", {"iliou-human", "iliou-advanced_bot"}),
        evaluate(ablated, rows, "Without raw timing: SapiMouse vs synthetic", {"sapimouse", "synthetic"}),
    ) if r]
    for r in ablation:
        print(f"  {r['set']}: stroke AUC {r['stroke_auc']}, session AUC {r['session_auc']}")
    for r in results:
        print(f"  {r['set']}: stroke AUC {r['stroke_auc']}, session AUC {r['session_auc']}, "
              f"session accuracy {r['session_accuracy']} ({r['sessions']} sessions)")

    exported = export(model)
    exported["evaluation"] = results
    max_diff = parity(model, exported, rows)
    print(f"  parity with scikit-learn: max |difference| {max_diff:.2e}")
    if max_diff > 1e-3:
        print("  WARNING: the exported model does not reproduce scikit-learn's probabilities")
    OUT_MODEL.write_text(json.dumps(exported, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT_MODEL} ({OUT_MODEL.stat().st_size / 1e6:.1f} MB)")

    importance = sorted(zip(FEATURE_NAMES, model.feature_importances_), key=lambda kv: -kv[1])
    lines = [
        "# Behaviour classifier - training report", "",
        f"Generated by `train.py` on {date.today().isoformat()}. Random forest, "
        f"{model.n_estimators} trees, depth <= 14, trained on single mouse strokes "
        "(continuous movements cut at pauses > 300 ms), kinematics on a 16 ms resampled path.", "",
        "## Data", "",
        "| Source | Split | Strokes |", "|---|---|---|",
        *[f"| {s} | {sp} | {n} |" for (s, sp), n in sorted(counts.items())], "",
        f"SapiMouse sessions: {sapi_sessions}. At most {MAX_STROKES_PER_SESSION} strokes per session, "
        "so no single long session dominates.", "",
        "## Held-out results", "",
        "Session score = mean of its strokes' bot probabilities; verdict at 0.5.", "",
        "| Test set | Sessions | Stroke AUC | Session AUC | Session accuracy |", "|---|---|---|---|---|",
        *[f"| {r['set']} | {r['sessions']} | {r['stroke_auc']} | {r['session_auc']} | {r['session_accuracy']} |" for r in results], "",
        "## Ablation: without raw-timing features", "",
        f"The same forest refitted without {', '.join(RAW_TIMING)} - the features computed on raw "
        "event timing, which could encode the recording device rather than the hand. If the "
        "held-out numbers hold up, the model separates humans from bots by the path itself.", "",
        "| Test set | Sessions | Stroke AUC | Session AUC | Session accuracy |", "|---|---|---|---|---|",
        *[f"| {r['set']} | {r['sessions']} | {r['stroke_auc']} | {r['session_auc']} | {r['session_accuracy']} |" for r in ablation], "",
        "## Export check", "",
        f"The backend scores runs by walking the exported trees in plain Python "
        f"(`app/behaviour/evaluation/mouse_model.py`). On {min(2000, sum(1 for r in rows if r[4] == 'test'))} "
        f"held-out strokes its probabilities differ from scikit-learn's by at most {max_diff:.1e}.", "",
        "## Feature importance", "",
        "| Feature | Importance |", "|---|---|",
        *[f"| {k} | {v:.3f} |" for k, v in importance], "",
        "## Caveats", "",
        "- Synthetic bots reuse each SapiMouse stroke's own endpoints, point count and timestamps, so they "
        "differ from the human stroke only in path shape and velocity profile. Their positions are rounded to "
        "whole pixels like real ones. The Iliou bots are real automation, which is why their held-out "
        "numbers matter more.",
        "- Phase 2 Iliou humans contributed two sessions each and are grouped by session, not by person.",
        "- Datasets were recorded with real mice at their own rates; Playwright input arrives through DevTools "
        "at roughly one event per frame. Resampling removes most of that difference, not necessarily all.",
        "",
        "## Sources", "",
        "- SapiMouse: M. Antal, N. Fejer, K. Buza, *SapiMouse: Mouse Dynamics-based User Authentication Using "
        "Deep Feature Learning*, SACI 2021. https://www.ms.sapientia.ro/~manyi/sapimouse/sapimouse.html",
        "- C. Iliou, T. Kostoulas, T. Tsikrika, V. Katos, S. Vrochidis, I. Kompatsiaris, *Detection of advanced "
        "web bots by combining web logs with mouse behavioural biometrics*, Digital Threats: Research and "
        "Practice, 2021. Dataset: https://m4d.iti.gr/web-bot-detection-dataset/ (CC BY-NC-SA 2.0)",
        "- A. Acien, A. Morales, J. Fierrez, R. Vera-Rodriguez, *BeCAPTCHA-Mouse: Synthetic Mouse Trajectories "
        "and Improved Bot Detection*, Pattern Recognition 127, 2022 - Method 1 re-implemented here; the "
        "benchmark data itself was not used.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
