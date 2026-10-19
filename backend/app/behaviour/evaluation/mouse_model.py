"""Scores a session's mouse movement with the trained behaviour classifier.

The model is a random forest trained by tests/behaviour/test_env/bot_model/
train.py on public human and bot mouse data (SapiMouse, the Iliou et al. web
bot dataset, and function-based synthetic trajectories after BeCAPTCHA-Mouse),
exported to JSON. Inference here walks those trees in plain Python, so scoring
a run needs nothing beyond the standard library.

It is an independent judge on purpose: it has never seen app.behaviour's own
output, nor the robotic control's, so whatever it says about them is not
something they were tuned against.
"""
from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.behaviour.evaluation.mouse_features import FEATURE_NAMES, features, moves_from_trace, strokes

MODEL_PATH = Path(__file__).with_name("mouse_model.json")
# Below this many strokes a session verdict is noise; the per-stroke numbers
# are still reported.
MIN_STROKES = 5


@lru_cache(maxsize=1)
def _load(path: str) -> dict:
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("features") != FEATURE_NAMES:
        raise RuntimeError(
            "mouse_model.json was trained on a different feature set - retrain it "
            "with tests/behaviour/test_env/bot_model/train.py"
        )
    return model


def model_available(path: Path = MODEL_PATH) -> bool:
    return path.exists()


def stroke_probability(vector: list[float], model: dict) -> float:
    """Mean over trees of the leaf's bot fraction, as scikit-learn's
    predict_proba computes it for a random forest.

    scikit-learn compares features as float32 against its thresholds, so the
    vector is rounded the same way first; comparing in float64 sends a value
    that falls between the two down the other branch.
    """
    vector = list(struct.unpack(f"{len(vector)}f", struct.pack(f"{len(vector)}f", *vector)))
    total = 0.0
    for tree in model["trees"]:
        node = 0
        left, right, feature, threshold, value = (
            tree["left"], tree["right"], tree["feature"], tree["threshold"], tree["value"],
        )
        while left[node] != -1:
            node = left[node] if vector[feature[node]] <= threshold[node] else right[node]
        total += value[node]
    return total / len(model["trees"])


def score_moves(moves, path: Path = MODEL_PATH) -> dict:
    """The classifier's view of one session's mouse movement."""
    model = _load(str(path))
    cut = strokes(moves)
    probabilities = [stroke_probability(features(s), model) for s in cut]
    threshold = model.get("threshold", 0.5)
    result: dict = {
        "model": model.get("name", "mouse-forest"),
        "trained_on": model.get("trained_on", []),
        "strokes": len(probabilities),
        "threshold": threshold,
    }
    if not probabilities:
        result["verdict"] = "no strokes long enough to judge"
        return result
    mean = sum(probabilities) / len(probabilities)
    ordered = sorted(probabilities)
    result.update({
        "bot_probability": round(mean, 3),
        "median_stroke": round(ordered[len(ordered) // 2], 3),
        "bot_like_strokes": sum(1 for p in probabilities if p >= threshold),
        "verdict": (
            "too few strokes for a verdict" if len(probabilities) < MIN_STROKES
            else "bot" if mean >= threshold else "human"
        ),
    })
    return result


def score_trace(trace: Optional[dict], path: Path = MODEL_PATH) -> dict:
    if not trace:
        return {"verdict": "no trace recorded"}
    return score_moves(moves_from_trace(trace), path)
