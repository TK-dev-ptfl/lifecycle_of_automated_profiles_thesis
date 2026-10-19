"""Plain measurements of a session's input, for comparing runs side by side.

The lab's checks and the classifier each give a verdict; this gives the
underlying numbers - how fast the cursor moved, how straight, how long buttons
were held, how evenly keys and wheel notches came - computed the same way for a
person driving the browser by hand, the behaviour algorithm, and the robotic
control. Where the verdicts disagree, these are what to look at.

All from the feed lab's __hearthTrace() export: times in ms since page load.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from app.behaviour.evaluation.mouse_features import FEATURE_NAMES, features, moves_from_trace, strokes

READING_PAUSE_MS = 700.0


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _cv(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean <= 0:
        return None
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) / mean


def _r(value: Optional[float], digits: int = 3) -> Optional[float]:
    return None if value is None else round(value, digits)


def trace_stats(trace: Optional[dict]) -> dict:
    """One flat dict of measurements; None where a session had nothing to
    measure (no typing, no clicks)."""
    if not trace:
        return {}
    moves = trace.get("moves", [])
    downs, ups = trace.get("downs", []), trace.get("ups", [])
    wheels, keys, scrolls = trace.get("wheels", []), trace.get("keys", []), trace.get("scrolls", [])

    times = [e[0] for group in (moves, downs, ups, wheels, keys) for e in group]
    duration_s = (max(times) - min(times)) / 1000 if len(times) > 1 else 0.0

    trusted = moves_from_trace(trace)
    cut = strokes(trusted)
    vectors = [features(s) for s in cut]
    col = {name: [v[i] for v in vectors] for i, name in enumerate(FEATURE_NAMES)}

    # Press length: each mousedown paired with the next mouseup.
    holds, j = [], 0
    for down in downs:
        while j < len(ups) and ups[j][0] < down[0]:
            j += 1
        if j < len(ups):
            holds.append(ups[j][0] - down[0])
            j += 1

    key_downs = [k[0] for k in keys if k[1] == "d" and not k[2]]
    key_ups = [k[0] for k in keys if k[1] == "u"]
    key_holds, j = [], 0
    for t in key_downs:
        while j < len(key_ups) and key_ups[j] < t:
            j += 1
        if j < len(key_ups):
            key_holds.append(key_ups[j] - t)
            j += 1
    key_gaps = [b - a for a, b in zip(key_downs, key_downs[1:]) if b - a < 1500]

    wheel_gaps = [b[0] - a[0] for a, b in zip(wheels, wheels[1:]) if b[0] - a[0] < 1000]
    scroll_px = sum(abs(b[1] - a[1]) for a, b in zip(scrolls, scrolls[1:]))
    pauses = sum(1 for a, b in zip(scrolls, scrolls[1:]) if b[0] - a[0] > READING_PAUSE_MS)

    return {
        "duration_s": _r(duration_s, 1),
        "mouse_moves": len(moves),
        "untrusted_moves": sum(1 for m in moves if len(m) > 3 and not m[3]),
        "moves_per_s": _r(len(moves) / duration_s if duration_s else None, 1),
        "strokes": len(cut),
        "stroke_straightness": _r(_median(col["straightness"])),
        "stroke_speed_px_ms": _r(_median(col["speed_mean"])),
        "stroke_peak_speed_px_ms": _r(_median(col["speed_max"])),
        "stroke_speed_cv": _r(_median(col["speed_cv"])),
        "stroke_turn_rad": _r(_median(col["turn_mean"]), 4),
        "stroke_end_speed_ratio": _r(_median(col["end_speed_ratio"])),
        "clicks": len(downs),
        "click_hold_ms": _r(_median(holds), 1),
        "click_hold_cv": _r(_cv(holds)),
        "wheel_events": len(wheels),
        "wheel_gap_ms": _r(_median(wheel_gaps), 1),
        "wheel_gap_cv": _r(_cv(wheel_gaps)),
        "scroll_px": round(scroll_px),
        "reading_pauses": pauses,
        "keys": len(key_downs),
        "key_hold_ms": _r(_median(key_holds), 1),
        "key_gap_cv": _r(_cv(key_gaps)),
    }
