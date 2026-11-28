#!/usr/bin/env python3
"""Jockey-upgrade differential feature (display / shadow only).

Definition: the win rate of the jockey booked today minus the mean win rate of
the jockeys who rode the horse in its last `prior_window` starts, all measured
strictly before the race date. A positive delta means the horse is switching to
a demonstrably stronger rider; the score maps delta onto the 0-100 factor scale
used by the nine-factor model.

Nothing here touches the live P_model. `build_asof_rates` is the leakage guard:
every rate uses only races whose date is strictly earlier than the query date,
with the same min-3-starts rule as the deployed jockey rate.
"""
from bisect import bisect_left
from collections import defaultdict

MIN_STARTS = 3
PRIOR_WINDOW = 6
SCORE_SLOPE = 500.0


def clip(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


class AsOfRates:
    """Cumulative jockey win rates, queryable for any date without look-ahead."""

    def __init__(self, rows, min_starts=MIN_STARTS):
        self.min_starts = min_starts
        by_day = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for row in rows:
            name = (row.get('jockey') or '').strip()
            date = str(row.get('race_date') or '')[:10]
            fp = row.get('finish_position')
            if not name or not date or fp is None or fp <= 0:
                continue
            entry = by_day[date][name]
            entry[0] += 1
            entry[1] += 1 if fp == 1 else 0

        self.dates = sorted(by_day)
        cumulative = defaultdict(lambda: [0, 0])
        self.after = {}
        for date in self.dates:
            for name, (starts, wins) in by_day[date].items():
                entry = cumulative[name]
                entry[0] += starts
                entry[1] += wins
            self.after[date] = {k: (v[0], v[1]) for k, v in cumulative.items()}

    def starts_wins(self, name, date):
        """Cumulative (starts, wins) from days strictly before `date`."""
        name = (name or '').strip()
        date = str(date or '')[:10]
        if not name or not date:
            return 0, 0
        index = bisect_left(self.dates, date) - 1
        if index < 0:
            return 0, 0
        return self.after[self.dates[index]].get(name, (0, 0))

    def rate(self, name, date):
        starts, wins = self.starts_wins(name, date)
        if starts < self.min_starts:
            return None, starts
        return wins / starts, starts


def _prior_runs(prior_runs, date, prior_window=PRIOR_WINDOW):
    runs = [r for r in prior_runs
            if str(r.get('race_date') or '')[:10] < str(date)[:10]]
    runs.sort(key=lambda r: str(r.get('race_date') or ''), reverse=True)
    return runs[:prior_window]


def feature_from_rates(current_jockey, current_rate, prior_rates,
                       prior_runs=0, prior_rated=0):
    """Score from a pre-resolved current rate and prior-jockey rates."""
    if current_rate is None or not prior_rates:
        return {
            'score': None, 'delta': None, 'current_rate': current_rate,
            'prior_mean': None, 'prior_runs': prior_runs, 'prior_rated': prior_rated,
        }
    prior_mean = sum(prior_rates) / len(prior_rates)
    delta = current_rate - prior_mean
    return {
        'score': round(clip(50.0 + SCORE_SLOPE * delta), 2),
        'delta': round(delta, 4),
        'current_rate': round(current_rate, 4),
        'prior_mean': round(prior_mean, 4),
        'prior_runs': prior_runs,
        'prior_rated': prior_rated,
    }


def feature_asof(asof, current_jockey, horse_history, date,
                 prior_window=PRIOR_WINDOW):
    """Compute the feature with strict as-of rates (backtest path)."""
    current_rate, _ = asof.rate(current_jockey, date)
    runs = _prior_runs(horse_history, date, prior_window)
    prior_rates = []
    for run in runs:
        rate, _ = asof.rate(run.get('jockey'), date)
        if rate is not None:
            prior_rates.append(rate)
    return feature_from_rates(current_jockey, current_rate, prior_rates,
                              prior_runs=len(runs), prior_rated=len(prior_rates))


def feature_from_stored(current_jockey, current_rate, horse_history, date,
                        prior_window=PRIOR_WINDOW):
    """Live shadow path: reuse stored jockey win rates from history rows.

    Stored rates were computed at scrape time from finished races only, so for
    a future race they contain no future information. The backtest always uses
    `feature_asof` instead, which recomputes rates at each race date.
    """
    runs = _prior_runs(horse_history, date, prior_window)
    prior_rates = [run['jockey_win_rate'] for run in runs
                   if run.get('jockey_win_rate') is not None]
    return feature_from_rates(current_jockey, current_rate, prior_rates,
                              prior_runs=len(runs), prior_rated=len(prior_rates))


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    num = sum((x - mx) * (y - my) for x, y in pairs)
    dx = sum((x - mx) ** 2 for x, _ in pairs) ** 0.5
    dy = sum((y - my) ** 2 for _, y in pairs) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)