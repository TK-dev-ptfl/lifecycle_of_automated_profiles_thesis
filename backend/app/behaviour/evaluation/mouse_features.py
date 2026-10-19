"""Mouse-movement features for telling a hand from a script.

Shared, unchanged, by the training script (tests/behaviour/test_env/bot_model)
and by run-time scoring, so a model is always applied to exactly the features
it was trained on. Plain Python on purpose: the backend scores runs without
numpy or scikit-learn installed.

The unit is a stroke: one continuous movement, cut out of the event stream at
pauses. Whole sessions differ too much in length and content to compare; single
strokes are where the motor signal is, and a session's verdict is built from
its strokes afterwards (see mouse_model).

Sampling rate is the trap. Datasets are recorded at different rates, and a
Playwright session delivers moves at yet another, so any feature that is really
"how often did events arrive" would teach a model which recorder made a trace,
not who moved the mouse. Kinematics are therefore computed on a path resampled
to a fixed 16 ms grid, and the few raw-timing features that remain are ones
where the difference is genuinely behavioural (a burst of moves in no time at
all is not something any mouse produces).
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

TimedPoint = tuple[float, float, float]  # (t_ms, x, y)

STEP_MS = 16.0
GAP_MS = 300.0
MIN_POINTS = 8
MIN_DISTANCE = 50.0
MAX_STROKE_MS = 6000.0

FEATURE_NAMES = [
    "log_duration_ms",
    "log_distance",
    "log_path_length",
    "straightness",
    "max_deviation_ratio",
    "log_raw_rate",
    "raw_dt_cv",
    "raw_dt_tiny_frac",
    "raw_step_cv",
    "axis_aligned_frac",
    "speed_mean",
    "speed_cv",
    "speed_max",
    "peak_position",
    "accel_std",
    "jerk_std",
    "turn_mean",
    "turn_std",
    "turn_zero_frac",
    "speed_peaks_per_s",
    "end_speed_ratio",
    "start_speed_ratio",
    "slow_frac",
]


def strokes(moves: Iterable[TimedPoint]) -> list[list[TimedPoint]]:
    """Cuts a stream of moves into strokes at pauses longer than GAP_MS (or a
    clock that runs backwards), keeping those long enough to say anything."""
    out: list[list[TimedPoint]] = []
    current: list[TimedPoint] = []
    for point in moves:
        if current:
            last = current[-1]
            if point == last:
                continue
            dt = point[0] - last[0]
            if dt > GAP_MS or dt < 0 or point[0] - current[0][0] > MAX_STROKE_MS:
                out.append(current)
                current = []
        current.append(point)
    if current:
        out.append(current)
    return [s for s in out if len(s) >= MIN_POINTS and _dist(s[0], s[-1]) >= MIN_DISTANCE]


def features(stroke: Sequence[TimedPoint]) -> list[float]:
    """The FEATURE_NAMES vector for one stroke."""
    t0, t1 = stroke[0][0], stroke[-1][0]
    duration = max(t1 - t0, 1.0)
    distance = _dist(stroke[0], stroke[-1])
    steps = [_dist(a, b) for a, b in zip(stroke, stroke[1:])]
    path = max(sum(steps), 1e-6)
    dts = [b[0] - a[0] for a, b in zip(stroke, stroke[1:])]
    moving = [(a, b) for a, b in zip(stroke, stroke[1:]) if (a[1], a[2]) != (b[1], b[2])]
    axis = sum(1 for a, b in moving if a[1] == b[1] or a[2] == b[2]) / max(len(moving), 1)

    grid = _resample(stroke)
    if grid is None or len(grid) < 4:
        # Too brief to resample: a burst. Kinematics come from the raw events
        # with a 1 ms floor on each interval - which is exactly what makes a
        # burst stand out.
        grid = stroke
        dt_of = [max(b[0] - a[0], 1.0) for a, b in zip(grid, grid[1:])]
    else:
        dt_of = [STEP_MS] * (len(grid) - 1)

    speeds = [_dist(a, b) / dt for (a, b), dt in zip(zip(grid, grid[1:]), dt_of)]
    accels = [(v2 - v1) / dt for v1, v2, dt in zip(speeds, speeds[1:], dt_of[1:])]
    jerks = [(a2 - a1) / dt for a1, a2, dt in zip(accels, accels[1:], dt_of[2:])]
    headings = [math.atan2(b[2] - a[2], b[1] - a[1]) for a, b in zip(grid, grid[1:]) if _dist(a, b) > 0.5]
    turns = [abs(_wrap(h2 - h1)) for h1, h2 in zip(headings, headings[1:])]

    v_max = max(speeds) if speeds else 0.0
    v_mean = _mean(speeds)
    fifth = max(1, len(speeds) // 5)
    smooth = _smooth(speeds)
    peaks = sum(
        1 for i in range(1, len(smooth) - 1)
        if smooth[i] > smooth[i - 1] and smooth[i] >= smooth[i + 1] and smooth[i] > 0.2 * v_max
    )

    return [
        math.log1p(duration),
        math.log1p(distance),
        math.log1p(path),
        min(distance / path, 1.0),
        _max_deviation(stroke) / max(distance, 1.0),
        math.log((len(stroke) - 1) / (duration / STEP_MS) + 1e-3),
        _cv(dts),
        sum(1 for d in dts if d < 4.0) / max(len(dts), 1),
        _cv(steps),
        axis,
        v_mean,
        v_mean and _std(speeds) / v_mean,
        v_max,
        (speeds.index(v_max) / max(len(speeds) - 1, 1)) if speeds else 0.0,
        _std(accels),
        _std(jerks),
        _mean(turns),
        _std(turns),
        (sum(1 for t in turns if t < 0.01) / len(turns)) if turns else 1.0,
        peaks / (duration / 1000.0),
        (_mean(speeds[-fifth:]) / v_max) if v_max else 0.0,
        (_mean(speeds[:fifth]) / v_max) if v_max else 0.0,
        (sum(1 for v in speeds if v < 0.05) / len(speeds)) if speeds else 0.0,
    ]


def moves_from_trace(trace: dict) -> list[TimedPoint]:
    """Trusted mousemoves from the feed lab's __hearthTrace() export."""
    return [(float(m[0]), float(m[1]), float(m[2])) for m in trace.get("moves", []) if len(m) < 4 or m[3]]


# --- helpers ---------------------------------------------------------------

def _resample(stroke: Sequence[TimedPoint]) -> Optional[list[TimedPoint]]:
    t0, t1 = stroke[0][0], stroke[-1][0]
    if t1 - t0 < 3 * STEP_MS:
        return None
    out: list[TimedPoint] = []
    j = 0
    t = t0
    while t <= t1:
        while j < len(stroke) - 2 and stroke[j + 1][0] < t:
            j += 1
        a, b = stroke[j], stroke[j + 1]
        span = b[0] - a[0]
        f = 0.0 if span <= 0 else min(max((t - a[0]) / span, 0.0), 1.0)
        out.append((t, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f))
        t += STEP_MS
    return out


def _max_deviation(stroke: Sequence[TimedPoint]) -> float:
    (_, x0, y0), (_, x1, y1) = stroke[0], stroke[-1]
    span = math.hypot(x1 - x0, y1 - y0)
    if span == 0:
        return 0.0
    return max(abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) / span for _, x, y in stroke)


def _smooth(values: list[float]) -> list[float]:
    if len(values) < 3:
        return values
    return [values[0]] + [(a + b + c) / 3 for a, b, c in zip(values, values[1:], values[2:])] + [values[-1]]


def _dist(a: TimedPoint, b: TimedPoint) -> float:
    return math.hypot(b[1] - a[1], b[2] - a[2])


def _wrap(angle: float) -> float:
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _cv(values: Sequence[float]) -> float:
    m = _mean(values)
    return _std(values) / m if m > 0 else 0.0
