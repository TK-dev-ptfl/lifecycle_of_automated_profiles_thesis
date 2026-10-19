"""The behaviour classifier's plumbing: stroke cutting, features, and the pure
Python forest walk. Model quality is measured by train.py on held-out data
(REPORT.md), not here - these tests pin that the numbers are computed right."""
from __future__ import annotations

import math

from app.behaviour.evaluation import mouse_model
from app.behaviour.evaluation.mouse_features import FEATURE_NAMES, features, moves_from_trace, strokes


def line(t0, n, dt, x0=100.0, dx=10.0):
    return [(t0 + i * dt, x0 + i * dx, 300.0) for i in range(n)]


def test_strokes_are_cut_at_pauses_and_short_ones_dropped():
    moves = line(0, 20, 16) + line(2000, 20, 16) + line(5000, 3, 16)  # last is too short
    cut = strokes(moves)
    assert len(cut) == 2
    assert all(len(s) == 20 for s in cut)


def test_a_stroke_has_one_finite_value_per_feature():
    vector = features(line(0, 30, 16))
    assert len(vector) == len(FEATURE_NAMES)
    assert all(math.isfinite(v) for v in vector)


def test_a_burst_of_moves_in_no_time_is_handled_and_stands_out():
    """Playwright's mouse.move(steps=N) sends N moves in about a millisecond."""
    burst = features(line(0, 10, 0.1))
    paced = features(line(0, 10, 16))
    tiny = FEATURE_NAMES.index("raw_dt_tiny_frac")
    assert burst[tiny] == 1.0 and paced[tiny] == 0.0
    assert all(math.isfinite(v) for v in burst)


def test_trace_export_keeps_only_trusted_moves():
    trace = {"moves": [[0, 1, 1, 1], [16, 2, 2, 0], [32, 3, 3, 1]]}
    assert moves_from_trace(trace) == [(0.0, 1.0, 1.0), (32.0, 3.0, 3.0)]


def test_forest_walk_averages_leaf_values_like_predict_proba():
    # Two stumps on feature 0: one says bot above 5, the other always 0.5.
    model = {"trees": [
        {"left": [1, -1, -1], "right": [2, -1, -1], "feature": [0, 0, 0], "threshold": [5.0, 0, 0], "value": [0, 0.0, 1.0]},
        {"left": [-1], "right": [-1], "feature": [0], "threshold": [0.0], "value": [0.5]},
    ]}
    assert mouse_model.stroke_probability([1.0], model) == 0.25
    assert mouse_model.stroke_probability([9.0], model) == 0.75


def test_the_shipped_model_matches_the_feature_set_and_scores_in_range():
    assert mouse_model.model_available()
    result = mouse_model.score_moves(line(0, 40, 16) + line(1000, 40, 16, x0=600, dx=-9))
    assert result["strokes"] == 2
    assert 0.0 <= result["bot_probability"] <= 1.0
    assert result["verdict"] == "too few strokes for a verdict"


def test_no_trace_is_reported_not_raised():
    assert mouse_model.score_trace(None)["verdict"] == "no trace recorded"
