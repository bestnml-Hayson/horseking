#!/usr/bin/env python3
"""Speed-rank vs model-rank shadow comparison (Line 2-D).

Shadow/display only: nothing here enters P_model, any factor weight or P_final.
The speed side reads race_runners.best_time — the career-best time HKJC prints
on the racecard for today's course/distance — so it is pre-race data. A true
speed figure from per-run finish_time/margin waits until those fields are fully
backfilled; this module only ranks the racecard best time within the field.

Runners without a usable best_time stay null: no constant imputation, and the
model's existing course/distance (trip) score is left untouched.
"""
import re
from statistics import mean

MIN_FIELD_TIMES = 4
TIME_MIN, TIME_MAX = 40.0, 240.0


def parse_best_time(raw):
    """'m.ss.hh' / 'm:ss.hh' -> seconds; numbers pass the range gate as-is.

    Mirrors lib/race-utils.ts parseBestTime so display and shadow agree.
    """
    if raw is None or raw == '':
        return None
    if isinstance(raw, (int, float)):
        seconds = float(raw)
        return seconds if TIME_MIN < seconds < TIME_MAX else None
    m = re.match(r'^(\d+)[.:](\d{2})[.:](\d{2})$', str(raw).strip())
    if not m:
        return None
    seconds = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100.0
    return seconds if TIME_MIN < seconds < TIME_MAX else None


def ranks(values, lower_is_better=False):
    """Competition ranks (1 + count strictly better); None stays None."""
    valid = [v for v in values if v is not None]
    if not valid:
        return [None] * len(values)
    return [
        None if v is None else
        1 + sum(1 for o in valid if (o < v if lower_is_better else o > v))
        for v in values
    ]


def speed_scores(times):
    """Within-race 0-100 score (fastest 100); None for missing or flat fields."""
    valid = [t for t in times if t is not None]
    if len(valid) < 2 or max(valid) == min(valid):
        return [None] * len(times)
    hi, lo = max(valid), min(valid)
    return [None if t is None else round(100.0 * (hi - t) / (hi - lo), 1)
            for t in times]


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks_out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks_out[order[k]] = avg
        i = j + 1
    return ranks_out


def spearman(xs, ys, min_pairs=4):
    """Spearman rho over paired non-null entries; None when n<min or flat."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < min_pairs:
        return None
    px, py = _average_ranks([p[0] for p in pairs]), _average_ranks([p[1] for p in pairs])
    mx, my = mean(px), mean(py)
    var_x = sum((v - mx) ** 2 for v in px)
    var_y = sum((v - my) ** 2 for v in py)
    if var_x <= 0 or var_y <= 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(px, py))
    return cov / (var_x * var_y) ** 0.5


def compare_runners(times, model_ranks, min_field_times=MIN_FIELD_TIMES):
    """Per-runner speed vs model rank for one race (meta, rows)."""
    parsed = [parse_best_time(t) for t in times]
    field_times = [t for t in parsed if t is not None]
    comparable = len(field_times) >= min_field_times
    speed_rank = ranks(parsed, lower_is_better=True)
    scores = speed_scores(parsed)
    if not comparable:
        speed_rank = [None] * len(parsed)
        scores = [None] * len(parsed)
    rows = []
    for i, t in enumerate(parsed):
        sr, mr = speed_rank[i], model_ranks[i] if i < len(model_ranks) else None
        rows.append({
            'best_time_sec': t,
            'speed_score': scores[i],
            'speed_rank': sr,
            'model_rank': mr,
            'rank_delta': (mr - sr) if sr is not None and mr is not None else None,
        })
    rho = spearman(speed_rank, model_ranks) if comparable else None
    meta = {
        'runners': len(parsed),
        'has_best_time': len(field_times),
        'coverage': round(len(field_times) / len(parsed), 4) if parsed else 0.0,
        'min_field_times': min_field_times,
        'comparable': comparable,
        'rank_corr': round(rho, 4) if rho is not None else None,
        'note': 'display-only; no weights; missing best_time stays null (trip score untouched)',
    }
    return meta, rows