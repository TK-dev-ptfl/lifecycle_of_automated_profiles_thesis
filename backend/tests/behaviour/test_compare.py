"""Comparing runs: the manual scenario's contract, the input statistics, and the
side-by-side table. No browser - runs are plain dicts here."""
from __future__ import annotations

import pytest

from app.behaviour.evaluation.trace_stats import trace_stats
from app.services import behaviour_run_service as service


def test_the_manual_scenario_differs_only_in_who_drives():
    human, manual = service.SCENARIOS["feed-lab"], service.SCENARIOS["feed-lab-manual"]
    assert manual.style == "manual"
    assert manual.schema is human.schema and manual.score_js == human.score_js
    assert "manual" in manual.url, "the lab only shows Finish with ?manual"


def test_stats_measure_holds_gaps_and_scrolling():
    trace = {
        "moves": [[i * 16, 100 + i * 10, 300, 1] for i in range(30)],
        "downs": [[1000, 5, 5, 0, 1], [2000, 5, 5, 0, 1]],
        "ups": [[1080, 5, 5, 0], [2120, 5, 5, 0]],
        "wheels": [[3000, 100, 0], [3050, 100, 0], [3100, 100, 0]],
        "keys": [[4000, "d", 0], [4060, "u", 0], [4200, "d", 0], [4250, "u", 0]],
        "scrolls": [[3000, 0], [3050, 100], [5000, 300]],
    }
    stats = trace_stats(trace)
    assert stats["mouse_moves"] == 30 and stats["strokes"] == 1
    assert stats["stroke_straightness"] == 1.0
    assert stats["clicks"] == 2 and stats["click_hold_ms"] == 100.0  # median of 80 and 120
    assert stats["wheel_events"] == 3 and stats["wheel_gap_ms"] == 50.0
    assert stats["keys"] == 2 and stats["key_hold_ms"] == 55.0
    assert stats["scroll_px"] == 300 and stats["reading_pauses"] == 1


def test_stats_of_a_session_with_no_input_are_empty_not_an_error():
    stats = trace_stats({"moves": [], "downs": [], "ups": [], "wheels": [], "keys": [], "scrolls": []})
    assert stats["mouse_moves"] == 0 and stats["click_hold_ms"] is None
    assert trace_stats(None) == {}


def test_compare_lines_runs_up_value_against_value(monkeypatch):
    runs = {
        "a": {"id": "a", "scenario": "feed-lab-manual", "style": "manual", "identity": "x",
              "score": {"overall": "97", "checks": [{"group": "beh", "name": "Imprecise aim", "state": "pass", "detail": "8 px"}]},
              "evaluation": {"mouse_model": {"verdict": "human", "bot_probability": 0.2, "strokes": 30, "bot_like_strokes": 4}},
              "stats": {"click_hold_ms": 95.0}},
        "b": {"id": "b", "scenario": "feed-lab-bot", "style": "robotic", "identity": "x",
              "score": {"overall": "10", "checks": [{"group": "beh", "name": "Imprecise aim", "state": "fail", "detail": "1 px"}]},
              "evaluation": {"mouse_model": {"verdict": "bot", "bot_probability": 0.8, "strokes": 10, "bot_like_strokes": 10}},
              "stats": {"click_hold_ms": 5.0}},
    }
    monkeypatch.setattr(service, "get_run", runs.get)
    table = service.compare(["a", "b", "missing"])

    assert [r["style"] for r in table["runs"]] == ["manual", "robotic"]
    row = {(r["section"], r["label"]): r["values"] for r in table["rows"]}
    assert row[("lab", "overall")] == ["97", "10"]
    assert row[("classifier", "bot probability")] == [0.2, 0.8]
    assert row[("classifier", "bot-like strokes")] == ["4/30", "10/10"]
    assert row[("input", "click_hold_ms")] == [95.0, 5.0]
    assert row[("lab check (behaviour)", "Imprecise aim")] == ["pass: 8 px", "fail: 1 px"]
    # A judge that did not run is a gap, not a crash.
    assert row[("detectors", "creepjs lies")] == [None, None]


def test_mann_whitney_auc_and_p_behave_at_the_extremes():
    from tests.behaviour.test_env.compare_runs import mann_whitney

    auc, p = mann_whitney([0.1, 0.2, 0.3, 0.15, 0.25], [0.7, 0.8, 0.9, 0.75, 0.85])
    assert auc == 1.0 and p < 0.05
    auc, p = mann_whitney([0.1, 0.5, 0.9], [0.1, 0.5, 0.9])
    assert auc == 0.5 and p > 0.9


def test_aggregate_groups_by_scenario_and_tests_against_the_manual_baseline():
    from tests.behaviour.test_env.compare_runs import aggregate

    runs = ([{"scenario": "feed-lab-manual", "_bot_probability": p} for p in (0.2, 0.25, 0.3)]
            + [{"scenario": "feed-lab-bot", "_bot_probability": p} for p in (0.7, 0.8, 0.9)])
    result = aggregate(runs)
    assert result["groups"] == {"feed-lab-manual": 3, "feed-lab-bot": 3}
    [(scenario, n_base, n, auc, _p)] = result["tests"]
    assert (scenario, n_base, n, auc) == ("feed-lab-bot", 3, 3, 1.0)
