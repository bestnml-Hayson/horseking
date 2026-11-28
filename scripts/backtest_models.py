#!/usr/bin/env python3
"""
Walk-forward evaluation for the Phase 1/2 quantitative upgrade.

Read-only against Supabase. It rebuilds every historical race with the same
9-factor formula the client uses, then:

  Phase 1
    - P_market de-vig: exponent grid 1.0-1.5, overall / venue / odds band,
      plus band-segmented exponents fitted walk-forward.
    - P_model calibration: raw, temperature, Platt, isotonic (fitted on the
      past, evaluated on the future only).
    - Fusion: alpha sweep + dynamic rules for extreme odds.

  Phase 2
    - Column coverage / variance gate (all-empty columns are excluded).
    - Feature ablations: best_time speed rank, official_rating rank,
      weight change vs last run, draw normalisation, form shrinkage.

  Output: console summary + reports/backtest_phase12_<date>.md and .json

IMPORTANT: race_runners.win_odds for meetings archived before v5.78 is a copy
of the SP dividend, so every ROI here is an SP-based upper bound, not a
placeable price. The report prints how many races carry genuine pre-race odds.

Usage:
  python scripts/backtest_models.py --since 2026-02-01
  python scripts/backtest_models.py --since 2026-06-01 --limit-races 80
"""
import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase, retry_supabase
import ai_review as A
from model_config import (MARKET_GAMMA, MODEL_WEIGHT, MARKET_WEIGHT,
                          SOFTMAX_TEMPERATURE, FACTOR_KEYS, weights_for)

HKT = ZoneInfo('Asia/Hong_Kong')

RUNNER_COLS = ('runner_id,race_id,horse_id,horse_no,draw,actual_weight,'
               'jockey_win_rate,trainer_win_rate,rest_days,gear,form_history,'
               'recent_form_score,finish_position,win_odds,best_time,'
               'official_rating,sectional_times,margin,finish_time')

HISTORY_COLS = ('horse_id,finish_position,actual_weight,sectional_times,'
                'races!inner(race_date,venue,distance,class_level)')

ODDS_BANDS = ((0.0, 4.0), (4.0, 10.0), (10.0, 10_000.0))
BAND_LABELS = ('熱門 ≤4', '中價 4-10', '冷門 >10')
CALIB_T_CANDIDATES = (4, 5, 6, 7, 8, 9, 10, 12, 14, 17, 20, 24)
EXTREME_ALPHA = 0.35
EXTREME_BAND = (1.8, 25.0)


def cache_path(since, limit):
    tag = since.replace('-', '') + (f'_top{limit}' if limit else '')
    return os.path.join(os.path.dirname(__file__), '..', 'reports', f'.samples_{tag}.json')


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_races(sb, since, limit=None):
    races, offset = [], 0
    while True:
        got = retry_supabase(lambda o=offset: sb.table('races')
            .select('race_id,race_date,venue,race_no,distance,class_level')
            .eq('is_finished', True)
            .gte('race_date', since)
            .in_('venue', ['HV', 'ST'])
            .order('race_id').range(o, o + 999).execute()).data or []
        races.extend(got)
        if len(got) < 1000:
            break
        offset += 1000
    races.sort(key=lambda r: (str(r['race_date']), r.get('race_no') or 0))
    if limit:
        races = races[-limit:]
    return races


def load_runners(sb, race_ids):
    by_race = defaultdict(list)
    for i in range(0, len(race_ids), 40):
        chunk = race_ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(lambda c=chunk, o=offset: sb.table('race_runners')
                .select(RUNNER_COLS).in_('race_id', c)
                .order('runner_id').range(o, o + 999).execute()).data or []
            for row in got:
                by_race[row['race_id']].append(row)
            if len(got) < 1000:
                break
            offset += 1000
    return by_race


def load_sp(sb, race_ids):
    """SP dividend per (race_id, horse_no) for the honesty check."""
    sp = {}
    for i in range(0, len(race_ids), 40):
        chunk = race_ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(lambda c=chunk, o=offset: sb.table('race_results')
                .select('race_id,horse_no,win_odds').in_('race_id', c)
                .order('race_id').range(o, o + 999).execute()).data or []
            for row in got:
                if row.get('win_odds'):
                    sp[(row['race_id'], row.get('horse_no'))] = float(row['win_odds'])
            if len(got) < 1000:
                break
            offset += 1000
    return sp


def fetch_history(sb, horse_ids):
    """One pass: finishes, class, run positions and carried weight (for weight change)."""
    hist = defaultdict(list)
    ids = list(horse_ids)
    for i in range(0, len(ids), 40):
        batch = ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(lambda b=batch, o=offset: sb.table('race_runners')
                .select(HISTORY_COLS).in_('horse_id', b)
                .not_.is_('finish_position', 'null')
                .order('runner_id').range(o, o + 999).execute()).data or []
            for row in got:
                fp = row.get('finish_position')
                if fp is None or fp <= 0:
                    continue
                race = row.get('races')
                if isinstance(race, list):
                    race = race[0] if race else None
                if not race or not race.get('venue') or not race.get('distance'):
                    continue
                hist[row['horse_id']].append({
                    'venue': race['venue'],
                    'distance': race['distance'],
                    'finish_position': fp,
                    'race_date': race.get('race_date', ''),
                    'class_level': race.get('class_level', ''),
                    'running_positions': row.get('sectional_times'),
                    'actual_weight': row.get('actual_weight'),
                })
            if len(got) < 1000:
                break
            offset += 1000
    for records in hist.values():
        records.sort(key=lambda r: r['race_date'], reverse=True)
    return hist


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def market_vector(odds, gamma, band_gammas=None):
    raw = []
    for o in odds:
        if o and o > 1:
            g = gamma
            if band_gammas:
                for (lo, hi), label in zip(ODDS_BANDS, BAND_LABELS):
                    if lo < o <= hi:
                        g = band_gammas[label]
                        break
            raw.append((1.0 / o) ** g)
        else:
            raw.append(0.0)
    total = sum(raw)
    if total <= 0:
        return [1.0 / max(1, len(odds))] * len(odds)
    return [r / total for r in raw]


def renormalise(ps):
    total = sum(ps)
    if total <= 0:
        return [1.0 / max(1, len(ps))] * len(ps)
    return [p / total for p in ps]


def softmax(scores, temperature=SOFTMAX_TEMPERATURE):
    if not scores:
        return []
    peak = max(scores)
    exps = [math.exp((s - peak) / temperature) for s in scores]
    total = sum(exps)
    return [e / total for e in exps] if total > 0 else [1.0 / len(scores)] * len(scores)


def winner_nll(ps, wi):
    return -math.log(max(ps[wi], 1e-12))


def top1(ps, wi):
    return 1 if max(range(len(ps)), key=lambda i: ps[i]) == wi else 0


def top3(ps, wi):
    order = sorted(range(len(ps)), key=lambda i: ps[i], reverse=True)
    return 1 if wi in order[:3] else 0


def brier(ps, wi):
    return sum((p - (1.0 if i == wi else 0.0)) ** 2 for i, p in enumerate(ps)) / len(ps)


def parse_best_time(raw):
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r'^(\d+)[.:](\d{2})[.:](\d{2})$', s)
    if not m:
        return None
    seconds = int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100.0
    return seconds if 40 < seconds < 240 else None


def pct_lower(values, v):
    """Percent of values strictly lower than v, ties count half (0-100)."""
    below = sum(1 for x in values if x < v)
    eq = sum(1 for x in values if x == v)
    return (below + 0.5 * eq) / max(len(values), 1) * 100.0


def clip(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x):
    if x < -40:
        return 0.0
    if x > 40:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------
# Sample building
# ---------------------------------------------------------------------------

def build_samples(sb, since, limit=None):
    races = load_races(sb, since, limit)
    print(f'[Load] {len(races)} finished HV/ST races since {since}')
    by_race = load_runners(sb, [r['race_id'] for r in races])

    horse_ids = {row['horse_id'] for rows in by_race.values() for row in rows if row.get('horse_id')}
    print(f'[Load] fetching history for {len(horse_ids)} horses...')
    history = fetch_history(sb, horse_ids)

    samples = []
    for race in races:
        rows = by_race.get(race['race_id'], [])
        finishers = [r for r in rows if (r.get('finish_position') or 0) > 0]
        winners = [r for r in finishers if r['finish_position'] == 1]
        if len(finishers) < 4 or len(winners) != 1:
            continue
        rows.sort(key=lambda r: r.get('horse_no') or 0)
        wi = rows.index(winners[0])
        odds = [r.get('win_odds') for r in rows]
        valid_odds = sum(1 for o in odds if o and o > 1)
        if valid_odds < 4 or not (odds[wi] and odds[wi] > 1):
            continue

        pace_label = A._predict_pace(rows, history, race['race_date'])
        factors = [
            A.compute_factor_scores(r, len(rows), race['venue'], race['distance'],
                                    race.get('class_level'), history, pace_label,
                                    race['race_date'])
            for r in rows
        ]
        weights = weights_for(race['venue'])
        total_scores = [sum(f[k] * weights[k] for k in FACTOR_KEYS) for f in factors]

        last_weights, form_positions = [], []
        for r in rows:
            prior = A._prior_starts(history.get(r.get('horse_id', ''), []), race['race_date'])
            last_weights.append(next((h['actual_weight'] for h in prior if h.get('actual_weight')), None))
            form_positions.append(A._recent_form_positions(r, prior))
        class_base = [
            A._compute_class_movement_score(r, race.get('class_level'), history, race['race_date'])
            for r in rows
        ]

        samples.append({
            'race_id': race['race_id'],
            'date': str(race['race_date'])[:10],
            'venue': race['venue'],
            'race_no': race.get('race_no'),
            'distance': race['distance'],
            'class_level': race.get('class_level'),
            'rows': rows,
            'winner_idx': wi,
            'odds': odds,
            'factors': factors,
            'weights': weights,
            'total_scores': total_scores,
            'p_model': softmax(total_scores),
            'best_times': [parse_best_time(r.get('best_time')) for r in rows],
            'ratings': [r.get('official_rating') for r in rows],
            'last_weights': last_weights,
            'form_positions': form_positions,
            'class_base': class_base,
            'avail': [
                A.factor_availability(r, len(rows), race['venue'], race['distance'],
                                      race.get('class_level'), history, race['race_date'])
                for r in rows
            ],
            'pace_label': pace_label,
        })

    samples.sort(key=lambda s: (s['date'], s['race_no'] or 0))
    print(f'[Load] {len(samples)} usable races / {sum(len(s["rows"]) for s in samples)} runners')
    return samples, races


def honesty_check(sb, samples, races):
    """Share of races whose stored win_odds differ from the SP dividend at all."""
    sample_ids = {s['race_id'] for s in samples}
    sp = load_sp(sb, list(sample_ids))
    genuine = 0
    compared = 0
    for s in samples:
        diffs = sum(
            1 for row, o in zip(s['rows'], s['odds'])
            if o and o > 1 and (s['race_id'], row.get('horse_no')) in sp
            and abs(float(sp[(s['race_id'], row.get('horse_no'))]) - o) > 1e-9
        )
        if diffs:
            genuine += 1
        compared += 1
    print(f'[Honesty] {genuine}/{compared} races carry genuine pre-race prices (rest are SP copies)')
    return {'races': compared, 'genuine_pre_race': genuine}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def evaluate(samples, prob_fn, key=None):
    """prob_fn(sample) -> list of probabilities aligned with sample rows."""
    nlls, briers, t1, t3 = [], [], 0, 0
    bets = rets = 0
    for s in samples:
        ps = prob_fn(s)
        wi = s['winner_idx']
        nlls.append(winner_nll(ps, wi))
        briers.append(brier(ps, wi))
        t1 += top1(ps, wi)
        t3 += top3(ps, wi)
        for i, o in enumerate(s['odds']):
            if o and o > 1 and ps[i] * o - 1 > 0:
                bets += 1
                if i == wi:
                    rets += o
    n = max(len(samples), 1)
    roi = (rets - bets) / bets * 100 if bets else None
    return {
        'races': len(samples),
        'nll': round(mean(nlls), 5) if nlls else None,
        'brier': round(mean(briers), 5) if briers else None,
        'top1': round(t1 / n, 4),
        'top3': round(t3 / n, 4),
        'bets': bets,
        'roi_pct': round(roi, 1) if roi is not None else None,
    }


def ece(samples, prob_fn, bins=10):
    pairs = []
    for s in samples:
        ps = prob_fn(s)
        for i, p in enumerate(ps):
            pairs.append((p, 1.0 if i == s['winner_idx'] else 0.0))
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])
    bucket = max(1, len(pairs) // bins)
    total = len(pairs)
    err = 0.0
    for start in range(0, total, bucket):
        chunk = pairs[start:start + bucket]
        if not chunk:
            continue
        avg_p = mean(p for p, _ in chunk)
        avg_y = mean(y for _, y in chunk)
        err += len(chunk) / total * abs(avg_p - avg_y)
    return round(err, 4)


# ---------------------------------------------------------------------------
# Walk-forward helpers
# ---------------------------------------------------------------------------

def split_blocks(samples, test_frac=0.4, folds=5):
    start = int(len(samples) * (1 - test_frac))
    test = samples[start:]
    size = max(1, len(test) // folds)
    blocks = []
    for k in range(folds):
        lo = k * size
        hi = len(test) if k == folds - 1 else (k + 1) * size
        blocks.append((samples[:start + lo], test[lo:hi]))
    return blocks


def fit_temperature(train):
    best = (None, None)
    for t in CALIB_T_CANDIDATES:
        nll = mean(winner_nll(softmax(s['total_scores'], t), s['winner_idx']) for s in train)
        if best[0] is None or nll < best[0]:
            best = (nll, t)
    return best[1]


def fit_platt(train):
    xs, ys = [], []
    for s in train:
        for i, p in enumerate(s['p_model']):
            xs.append(logit(p))
            ys.append(1.0 if i == s['winner_idx'] else 0.0)
    a, b = 1.0, 0.0
    for _ in range(60):
        g0 = g1 = 0.0
        h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            p = sigmoid(a * x + b)
            err = p - y
            g0 += err * x
            g1 += err
            w = p * (1 - p)
            h00 += w * x * x
            h01 += w * x
            h11 += w
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (-h01 * g0 + h00 * g1) / det
        a -= da
        b -= db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def fit_isotonic(train):
    pairs = sorted(
        (p, 1.0 if i == s['winner_idx'] else 0.0)
        for s in train for i, p in enumerate(s['p_model'])
    )
    blocks = [[1.0, y, x, x] for x, y in pairs]  # weight, sum_y, min_x, max_x
    merged = []
    for block in blocks:
        merged.append(block)
        while len(merged) >= 2 and merged[-2][1] / merged[-2][0] > merged[-1][1] / merged[-1][0]:
            b2 = merged.pop()
            b1 = merged.pop()
            merged.append([b1[0] + b2[0], b1[1] + b2[1], b1[2], b2[3]])
    return [(lo, hi, sy / w) for w, sy, lo, hi in merged]


def apply_isotonic(knots, p):
    if not knots:
        return p
    for lo, hi, value in knots:
        if p <= hi:
            return value
    return knots[-1][2]


# ---------------------------------------------------------------------------
# Feature variants
# ---------------------------------------------------------------------------

def pre_phase2_factors(sample):
    """Reverse the three merged Phase-2 formulas so each ablation starts from the
    pre-Phase-2 baseline: form without shrinkage, the old draw normalisation and
    class movement without the official_rating blend."""
    rows = sample['rows']
    n = len(rows)
    factors = [dict(f) for f in sample['factors']]
    for i, row in enumerate(rows):
        positions = sample['form_positions'][i]
        if positions:
            avg = sum(positions) / len(positions)
            factors[i]['form'] = clip((1 - (avg - 1) / 13) * 100)
        d = row.get('draw')
        if d is not None:
            factors[i]['draw'] = clip((1 - (d - 1) / max(1, n - 1)) * 100)
        factors[i]['classMov'] = clip(sample['class_base'][i])
    return factors


def variant_factor_scores(sample, name, blend, base=None):
    """Return adjusted factor dicts for one race (None when variant inapplicable)."""
    rows = sample['rows']
    n = len(rows)
    factors = [dict(f) for f in (base if base is not None else pre_phase2_factors(sample))]

    if name == 'speed':
        times = sample['best_times']
        have = [(i, t) for i, t in enumerate(times) if t]
        if len(have) < 4:
            return None
        pool = [t for _, t in have]
        for i, t in have:
            score = 100.0 - pct_lower(pool, t)
            factors[i]['form'] = (1 - blend) * factors[i]['form'] + blend * score
        return factors

    if name == 'rating':
        ratings = [(i, r) for i, r in enumerate(sample['ratings']) if r is not None]
        if len(ratings) < 4:
            return None
        pool = [r for _, r in ratings]
        for i, r in ratings:
            score = pct_lower(pool, r)
            factors[i]['classMov'] = (1 - blend) * factors[i]['classMov'] + blend * score
        return factors

    if name in ('weight_change', 'weight_full'):
        weights = [r.get('actual_weight') for r in rows]
        have = [(i, w) for i, w in enumerate(weights) if w]
        if len(have) < 4:
            return None
        field_avg = mean(w for _, w in have)
        changed = False
        for i, w in have:
            base = factors[i]['weight']
            last = sample['last_weights'][i]
            if name == 'weight_change':
                if not last:
                    continue
                changed = True
                factors[i]['weight'] = 0.5 * base + 0.5 * clip(50 + 3.0 * (last - w))
            else:
                rel = clip(50 + 2.0 * (field_avg - w))
                if last:
                    chg = clip(50 + 3.0 * (last - w))
                    factors[i]['weight'] = 0.5 * base + 0.3 * rel + 0.2 * chg
                else:
                    factors[i]['weight'] = 0.6 * base + 0.4 * rel
        if name == 'weight_change' and not changed:
            return None
        return factors

    if name == 'draw_v2':
        for i, row in enumerate(rows):
            d = row.get('draw')
            if d is None:
                continue
            norm = (d - 1) / max(1, n - 1)
            k = 0.9 if sample['venue'] == 'HV' else (0.7 if (sample['distance'] or 0) < 1600 else 0.55)
            factors[i]['draw'] = clip((1 - k * norm) * 100)
        return factors

    if name == 'form_shrink':
        used = False
        for i in range(n):
            positions = sample['form_positions'][i]
            if len(positions) < 2:
                continue
            used = True
            avg = sum(positions) / len(positions)
            shrunk = (len(positions) * avg + 2.5 * 6.5) / (len(positions) + 2.5)
            factors[i]['form'] = clip((1 - (shrunk - 1) / 13) * 100)
        return factors if used else None

    return None


def p_model_from_factors(sample, factors, temperature=SOFTMAX_TEMPERATURE):
    scores = [sum(f[k] * sample['weights'][k] for k in FACTOR_KEYS) for f in factors]
    return softmax(scores, temperature)


def avail_p_model(sample, factors=None):
    """Scores with the weights of missing-input factors removed and renormalised."""
    factors = factors if factors is not None else sample['factors']
    scores = []
    for i, fac in enumerate(factors):
        used = [k for k in FACTOR_KEYS if sample['avail'][i].get(k, True)]
        wsum = sum(sample['weights'][k] for k in used) or 1.0
        scores.append(sum(fac[k] * sample['weights'][k] for k in used) / wsum)
    return softmax(scores)


def combined_features(sample):
    """The deployed Phase-2 factor formulas, rebuilt from the pre-Phase-2 base."""
    rows = sample['rows']
    n = len(rows)
    factors = pre_phase2_factors(sample)
    pool = [r for r in sample['ratings'] if r is not None]
    for i, row in enumerate(rows):
        positions = sample['form_positions'][i]
        if positions:
            avg = sum(positions) / len(positions)
            shrunk = (len(positions) * avg + 2.5 * 6.5) / (len(positions) + 2.5)
            factors[i]['form'] = clip((1 - (shrunk - 1) / 13) * 100)
        d = row.get('draw')
        if d is not None:
            norm = (d - 1) / max(1, n - 1)
            k = 0.9 if sample['venue'] == 'HV' else (0.7 if (sample['distance'] or 0) < 1600 else 0.55)
            factors[i]['draw'] = clip((1 - k * norm) * 100)
        rating = row.get('official_rating')
        if rating is not None and len(pool) >= 4:
            factors[i]['classMov'] = clip(0.65 * factors[i]['classMov'] + 0.35 * pct_lower(pool, rating))
    return factors


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(x, digits=4):
    return '-' if x is None else f'{x:.{digits}f}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', default='2026-02-01')
    parser.add_argument('--limit-races', type=int, default=None)
    parser.add_argument('--test-frac', type=float, default=0.4)
    parser.add_argument('--folds', type=int, default=5)
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--out-dir', default=os.path.join(os.path.dirname(__file__), '..', 'reports'))
    args = parser.parse_args()

    sb = get_supabase()
    cpath = cache_path(args.since, args.limit_races)
    if os.path.exists(cpath) and not args.no_cache:
        with open(cpath, encoding='utf-8') as fh:
            cached = json.load(fh)
        samples, races = cached['samples'], cached['races']
        print(f'[Load] {len(samples)} races from cache {os.path.basename(cpath)}')
    else:
        samples, races = build_samples(sb, args.since, args.limit_races)
        if not args.no_cache:
            os.makedirs(os.path.dirname(cpath), exist_ok=True)
            with open(cpath, 'w', encoding='utf-8') as fh:
                json.dump({'samples': samples, 'races': races}, fh, ensure_ascii=False)
    if len(samples) < 60:
        print('[Abort] fewer than 60 usable races')
        return 1

    honesty = honesty_check(sb, samples, races)
    blocks = split_blocks(samples, args.test_frac, args.folds)
    test_all = [s for _, test in blocks for s in test]
    block_of = {}
    for k, (_, test) in enumerate(blocks):
        for s in test:
            block_of[s['race_id']] = k
    print(f'[Eval] walk-forward: {len(blocks)} folds, {len(test_all)} test races '
          f'({test_all[0]["date"]} → {test_all[-1]["date"]})')

    def model_of(s, t=SOFTMAX_TEMPERATURE):
        return softmax(s['total_scores'], t)

    def market_of(s, gamma, band_gammas=None):
        return market_vector(s['odds'], gamma, band_gammas)

    def fused_of(s, alpha, gamma=MARKET_GAMMA, calib=None):
        pm = model_of(s) if calib is None else calib(s)
        pmk = market_of(s, gamma)
        return [alpha * pm[i] + (1 - alpha) * pmk[i] for i in range(len(pm))]

    # ---- data quality gate -------------------------------------------------
    all_rows = [r for s in samples for r in s['rows']]
    gate_fields = {
        'draw': lambda r: r.get('draw') is not None,
        'actual_weight': lambda r: r.get('actual_weight') is not None,
        'jockey_win_rate': lambda r: r.get('jockey_win_rate') is not None,
        'trainer_win_rate': lambda r: r.get('trainer_win_rate') is not None,
        'rest_days': lambda r: r.get('rest_days') is not None,
        'gear': lambda r: bool(r.get('gear')),
        'form_history': lambda r: bool(r.get('form_history')),
        'best_time': lambda r: parse_best_time(r.get('best_time')) is not None,
        'official_rating': lambda r: r.get('official_rating') is not None,
        'sectional_times': lambda r: bool(r.get('sectional_times')),
        'last_weight (history)': lambda r: False,  # filled below
        'margin': lambda r: r.get('margin') is not None,
        'finish_time': lambda r: r.get('finish_time') is not None,
    }
    last_weight_ok = sum(
        1 for s in samples for i, r in enumerate(s['rows']) if s['last_weights'][i] is not None
    )
    gate = {}
    for name, fn in gate_fields.items():
        if name == 'last_weight (history)':
            cov = last_weight_ok / max(len(all_rows), 1)
        else:
            cov = sum(1 for r in all_rows if fn(r)) / max(len(all_rows), 1)
        gate[name] = round(cov, 4)
    usable = {k: v for k, v in gate.items() if v >= 0.2 and k not in ('margin', 'finish_time')}
    excluded = {k: v for k, v in gate.items() if k not in usable}
    print('[Gate] usable:', ', '.join(f'{k} {v*100:.0f}%' for k, v in usable.items()))
    print('[Gate] excluded:', ', '.join(f'{k} {v*100:.0f}%' for k, v in excluded.items()) or 'none')

    # ---- Phase 1: market de-vig -------------------------------------------
    gamma_grid = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5)
    gamma_rows = []
    for g in gamma_grid:
        res = evaluate(test_all, lambda s, gg=g: market_of(s, gg))
        res['gamma'] = g
        gamma_rows.append(res)
    print('\n[P_market] gamma grid (OOS evaluation):')
    for row in gamma_rows:
        print(f"  γ={row['gamma']:.1f}  NLL {row['nll']:.5f}  Brier {row['brier']:.5f}")

    gamma_picks = []
    for train, _ in blocks:
        gamma_picks.append(min(gamma_grid, key=lambda g: mean(
            winner_nll(market_of(s, g), s['winner_idx']) for s in train)))
    gamma_wf = evaluate(test_all, lambda s: market_of(s, gamma_picks[block_of[s['race_id']]]))
    gamma_deploy = max(set(gamma_picks), key=gamma_picks.count)
    print(f'[P_market] walk-forward picks {gamma_picks} → NLL {gamma_wf["nll"]:.5f} '
          f'(deploy γ={gamma_deploy})')

    band_grid = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6)
    band_picks_wf = []
    for train, _ in blocks:
        picks = {label: gamma_deploy for label in BAND_LABELS}
        for _pass in range(2):
            for label in BAND_LABELS:
                best = None
                for g in band_grid:
                    trial = dict(picks)
                    trial[label] = g
                    nll = mean(winner_nll(market_of(s, gamma_deploy, trial), s['winner_idx'])
                               for s in train)
                    if best is None or nll < best[0]:
                        best = (nll, g)
                picks[label] = best[1]
        band_picks_wf.append(picks)
    band_wf = evaluate(test_all, lambda s: market_of(
        s, gamma_deploy, band_picks_wf[block_of[s['race_id']]]))
    band_deploy = {label: max(set(p[label] for p in band_picks_wf),
                              key=[p[label] for p in band_picks_wf].count)
                   for label in BAND_LABELS}
    band_deploy_res = evaluate(test_all, lambda s: market_of(s, gamma_deploy, band_deploy))
    gamma_deploy_res = evaluate(test_all, lambda s: market_of(s, gamma_deploy))
    # Banded γ only counts if its single deployed table beats one global γ on test.
    band_helps = band_deploy_res['nll'] < gamma_deploy_res['nll'] - 0.001
    print(f'[P_market] walk-forward banded {band_picks_wf} → NLL {band_wf["nll"]:.5f}; '
          f'deploy {band_deploy} → NLL {band_deploy_res["nll"]:.5f} '
          f'({"deploy banded" if band_helps else "keep single γ"})')

    by_venue_market = {}
    for venue in ('HV', 'ST'):
        subset = [s for s in test_all if s['venue'] == venue]
        by_venue_market[venue] = evaluate(subset, lambda s: market_of(s, gamma_deploy))

    # ---- Phase 1: P_model calibration (walk-forward) -----------------------
    calib_metrics = {'raw': evaluate(test_all, lambda s: model_of(s))}
    temps, platts, isos = [], [], []
    platt_probs = {}
    iso_probs = {}
    temp_probs = {}
    for train, test in blocks:
        t = fit_temperature(train)
        a, b = fit_platt(train)
        knots = fit_isotonic(train)
        temps.append(t)
        platts.append((round(a, 4), round(b, 4)))
        isos.append(len(knots))
        for s in test:
            temp_probs[s['race_id']] = softmax(s['total_scores'], t)
            platt_probs[s['race_id']] = renormalise(
                [sigmoid(a * logit(p) + b) for p in s['p_model']])
            iso_probs[s['race_id']] = renormalise(
                [apply_isotonic(knots, p) for p in s['p_model']])
    calib_metrics['temperature'] = evaluate(test_all, lambda s: temp_probs[s['race_id']])
    calib_metrics['platt'] = evaluate(test_all, lambda s: platt_probs[s['race_id']])
    calib_metrics['isotonic'] = evaluate(test_all, lambda s: iso_probs[s['race_id']])
    calib_ece = {
        'raw': ece(test_all, lambda s: model_of(s)),
        'temperature': ece(test_all, lambda s: temp_probs[s['race_id']]),
        'platt': ece(test_all, lambda s: platt_probs[s['race_id']]),
        'isotonic': ece(test_all, lambda s: iso_probs[s['race_id']]),
    }
    best_calib = min(calib_metrics, key=lambda k: calib_metrics[k]['nll'])
    print('\n[P_model] calibration (walk-forward OOS):')
    for name, res in calib_metrics.items():
        print(f"  {name:12s} NLL {res['nll']:.5f}  Brier {res['brier']:.5f}  "
              f"ECE {calib_ece[name]}  top1 {res['top1']:.3f}")
    print(f'  temperature fold T={temps}, platt fold (a,b)={platts}, isotonic knots={isos}')

    # ---- Phase 1: fusion ---------------------------------------------------
    alpha_rows = []
    for i in range(0, 11):
        alpha = i / 20.0
        res = evaluate(test_all, lambda s, a=alpha: fused_of(s, a, gamma_deploy))
        res['alpha'] = alpha
        alpha_rows.append(res)
    best_alpha = min(alpha_rows, key=lambda r: r['nll'])['alpha']
    print('\n[Fusion] alpha sweep (OOS evaluation):')
    for row in alpha_rows:
        print(f"  α={row['alpha']:.2f}  NLL {row['nll']:.5f}  top1 {row['top1']:.3f}  "
              f"ROI {fmt(row['roi_pct'], 1)}%")

    alpha_picks = []
    for train, _ in blocks:
        alpha_picks.append(min((i / 20.0 for i in range(0, 11)), key=lambda a: mean(
            winner_nll(fused_of(s, a, gamma_deploy), s['winner_idx']) for s in train)))
    alpha_wf = evaluate(test_all, lambda s: fused_of(
        s, alpha_picks[block_of[s['race_id']]], gamma_deploy))
    print(f'[Fusion] walk-forward α picks {alpha_picks} → NLL {alpha_wf["nll"]:.5f}')

    dynamic_rows = []
    for cut_lo, cut_hi, alt in ((2.0, 30.0, 0.35), (2.0, 30.0, 0.45), (1.8, 25.0, 0.35)):
        def dyn(s, lo=cut_lo, hi=cut_hi, a=alt):
            pm = model_of(s)
            pmk = market_of(s, gamma_deploy)
            out = []
            for i, o in enumerate(s['odds']):
                alpha = a if (o and (o < lo or o > hi)) else MODEL_WEIGHT
                out.append(alpha * pm[i] + (1 - alpha) * pmk[i])
            return out
        res = evaluate(test_all, dyn)
        res['rule'] = f'α={alt} if odds<{cut_lo} or >{cut_hi}'
        dynamic_rows.append(res)
    print('[Fusion] dynamic extreme-odds rules:')
    for row in dynamic_rows:
        print(f"  {row['rule']}  NLL {row['nll']:.5f}  top1 {row['top1']:.3f}  ROI {fmt(row['roi_pct'], 1)}%")

    # ---- Phase 2: feature ablations ---------------------------------------
    variants = [
        ('speed', 0.25), ('speed', 0.40),
        ('rating', 0.35), ('rating', 0.50),
        ('weight_change', None), ('weight_full', None),
        ('draw_v2', None), ('form_shrink', None),
    ]
    variant_results = {}
    for name, blend in variants:
        subset = []
        adjusted = {}
        for s in test_all:
            f = variant_factor_scores(s, name, blend)
            if f is None:
                continue
            subset.append(s)
            adjusted[s['race_id']] = p_model_from_factors(s, f)
        if len(subset) < 40:
            continue
        base = evaluate(subset, lambda s: p_model_from_factors(s, pre_phase2_factors(s)))
        var = evaluate(subset, lambda s, adj=adjusted: adj[s['race_id']])
        key = name if blend is None else f'{name}_{int(blend*100)}'
        variant_results[key] = {
            'races': len(subset),
            'baseline': base,
            'variant': var,
            'delta_nll': round(var['nll'] - base['nll'], 5),
            'delta_top1': round(var['top1'] - base['top1'], 4),
        }

    base_all = evaluate(test_all, lambda s: p_model_from_factors(s, pre_phase2_factors(s)))
    for key, fn in (
        ('avail_aware', lambda s: avail_p_model(s, pre_phase2_factors(s))),
        ('phase2_combined', lambda s: p_model_from_factors(s, combined_features(s))),
    ):
        var = evaluate(test_all, fn)
        variant_results[key] = {
            'races': len(test_all),
            'baseline': base_all,
            'variant': var,
            'delta_nll': round(var['nll'] - base_all['nll'], 5),
            'delta_top1': round(var['top1'] - base_all['top1'], 4),
        }
    print('\n[Features] walk-forward ablations on their own coverage subset:')
    for key, res in variant_results.items():
        print(f"  {key:16s} n={res['races']:3d}  NLL {res['baseline']['nll']:.5f} → "
              f"{res['variant']['nll']:.5f} (Δ{res['delta_nll']:+.5f})  "
              f"top1 {res['baseline']['top1']:.3f} → {res['variant']['top1']:.3f}")

    # ---- final comparison rows --------------------------------------------
    calib_t = sorted(temps)[len(temps) // 2]
    power = SOFTMAX_TEMPERATURE / calib_t

    def phase2_p_model(s):
        # Deployed path: the accepted Phase-2 feature formulas only. The
        # availability-aware renormalisation measured +0.021 NLL and ships as
        # UI 待定 flags, not as weight changes.
        return p_model_from_factors(s, combined_features(s))

    def calibrated(pm):
        return renormalise([p ** power for p in pm])

    def market_deploy(s):
        return market_of(s, gamma_deploy, band_deploy if band_helps else None)

    def fused_stage(model_fn, alpha_fn=None):
        def fn(s):
            pm = model_fn(s)
            pmk = market_deploy(s)
            out = []
            for i, o in enumerate(s['odds']):
                a = alpha_fn(s, i, o) if alpha_fn else MODEL_WEIGHT
                out.append(a * pm[i] + (1 - a) * pmk[i])
            return out
        return fn

    def extreme_alpha(s, i, o):
        if o and (o < EXTREME_BAND[0] or o > EXTREME_BAND[1]):
            return EXTREME_ALPHA
        return MODEL_WEIGHT

    production = evaluate(test_all, lambda s: fused_of(s, MODEL_WEIGHT, 1.3))
    step_gamma = evaluate(test_all, fused_stage(lambda s: s['p_model']))
    step_features = evaluate(test_all, fused_stage(phase2_p_model))
    step_calib = evaluate(test_all, fused_stage(lambda s: calibrated(phase2_p_model(s))))
    step_dynamic = evaluate(test_all, fused_stage(
        lambda s: calibrated(phase2_p_model(s)), extreme_alpha))
    staged = {
        '部署前基線 (γ1.3 raw)': production,
        '+γ': step_gamma,
        '+features (deployed)': step_features,
        '+calibration': step_calib,
        '+dynamic α': step_dynamic,
    }

    weights_source = {}
    try:
        from model_config import ACTIVE_WEIGHTS_PATH
        with open(ACTIVE_WEIGHTS_PATH, encoding='utf-8') as fh:
            active = json.load(fh)
        weights_source = {
            'fitted_at': active.get('fitted_at'),
            'sample_races': active.get('sample_races'),
            'table': active.get('weights'),
        }
    except (OSError, ValueError):
        weights_source = {'fitted_at': None, 'sample_races': None, 'table': None}
    print(f'\n[Final] staged proposal (γ={gamma_deploy}, T={calib_t}, '
          f'α={MODEL_WEIGHT}, extreme α={EXTREME_ALPHA} @ {EXTREME_BAND}):')
    for name, res in staged.items():
        print(f"  {name:22s} NLL {res['nll']:.5f}  top1 {res['top1']:.3f}  "
              f"top3 {res['top3']:.3f}  ROI {fmt(res['roi_pct'], 1)}%")

    # ---- write report ------------------------------------------------------
    os.makedirs(args.out_dir, exist_ok=True)
    day = datetime.now(HKT).strftime('%Y-%m-%d')
    payload = {
        'generated_at': datetime.now(HKT).isoformat(),
        'since': args.since,
        'races': len(samples),
        'runners': sum(len(s['rows']) for s in samples),
        'test_races': len(test_all),
        'test_window': [test_all[0]['date'], test_all[-1]['date']],
        'honesty': honesty,
        'gate': gate,
        'market_gamma': gamma_rows,
        'gamma_picks': gamma_picks,
        'gamma_wf': gamma_wf,
        'gamma_deploy': gamma_deploy,
        'band_picks_wf': band_picks_wf,
        'band_deploy': band_deploy,
        'band_wf': band_wf,
        'band_deploy_result': band_deploy_res,
        'band_deploy_active': band_helps,
        'by_venue_market': by_venue_market,
        'calibration': calib_metrics,
        'calibration_ece': calib_ece,
        'calibration_params': {'temperature': temps, 'platt': platts, 'isotonic_knots': isos},
        'calibration_t_deploy': calib_t,
        'best_calibration': best_calib,
        'fusion_alpha': alpha_rows,
        'fusion_best_alpha': best_alpha,
        'fusion_alpha_picks': alpha_picks,
        'fusion_alpha_wf': alpha_wf,
        'fusion_dynamic': dynamic_rows,
        'staged': staged,
        'weights_source': weights_source,
        'features': variant_results,
    }
    json_path = os.path.join(args.out_dir, f'backtest_phase12_{day}.json')
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    md = []
    md.append(f'# Phase 1/2 Walk-Forward 回測報告（{day}）\n')
    md.append(f"- 樣本：{len(samples)} 場（{samples[0]['date']} → {samples[-1]['date']}），"
              f"{payload['runners']} 匹；測試段 {len(test_all)} 場（{payload['test_window'][0]} → {payload['test_window'][1]}）")
    md.append(f"- 真實賽前賠率：{honesty['genuine_pre_race']}/{honesty['races']} 場"
              f"（其餘為 SP 複製，ROI 只可作上限參考）\n")
    md.append('## 數據質量門禁\n')
    md.append('| 欄位 | 非空率 | 判定 |\n|---|---|---|')
    for name, cov in gate.items():
        verdict = '可用' if name in usable else '排除（全空/覆蓋不足）'
        md.append(f'| {name} | {cov*100:.1f}% | {verdict} |')
    md.append('\n## P_market 去水\n')
    md.append('| γ | NLL | Brier |\n|---|---|---|')
    for row in gamma_rows:
        md.append(f"| {row['gamma']:.1f} | {row['nll']:.5f} | {row['brier']:.5f} |")
    md.append(f"\nWalk-forward 選 γ：每折 {gamma_picks} → NLL {gamma_wf['nll']:.5f}；"
              f"部署 γ={gamma_deploy}")
    md.append(f"Walk-forward 分段 γ：每折 {band_picks_wf}")
    md.append(f"分段部署 {band_deploy} → NLL {band_deploy_res['nll']:.5f}"
              f"（{'採用' if band_helps else '不採用，維持單一 γ'}）\n")
    md.append('## P_model 校準（walk-forward OOS）\n')
    md.append('| 方法 | NLL | Brier | ECE | Top-1 | Top-3 |\n|---|---|---|---|---|---|')
    for name, res in calib_metrics.items():
        md.append(f"| {name} | {res['nll']:.5f} | {res['brier']:.5f} | {calib_ece[name]} | "
                  f"{res['top1']:.3f} | {res['top3']:.3f} |")
    md.append(f"\nTemperature folds: {temps}（部署 T={calib_t}）；Platt folds: {platts}；"
              f"Isotonic knots: {isos}\n")
    md.append('## 融合\n')
    md.append('| α | NLL | Top-1 | ROI (SP) |\n|---|---|---|---|')
    for row in alpha_rows:
        md.append(f"| {row['alpha']:.2f} | {row['nll']:.5f} | {row['top1']:.3f} | {fmt(row['roi_pct'], 1)}% |")
    md.append(f"\nWalk-forward 選 α：每折 {alpha_picks} → NLL {alpha_wf['nll']:.5f}"
              f"（核心 α 固定 0.2，僅作診斷）\n")
    md.append('動態極端賠率規則：\n')
    for row in dynamic_rows:
        md.append(f"- {row['rule']}：NLL {row['nll']:.5f}，Top-1 {row['top1']:.3f}，ROI {fmt(row['roi_pct'],1)}%")
    md.append('\n## Phase 2 特徵消融（同一覆蓋子集，測試段）\n')
    md.append('| 變體 | 場數 | 基線 NLL | 變體 NLL | ΔNLL | 基線 Top-1 | 變體 Top-1 |\n|---|---|---|---|---|---|---|')
    for key, res in variant_results.items():
        md.append(f"| {key} | {res['races']} | {res['baseline']['nll']:.5f} | {res['variant']['nll']:.5f} | "
                  f"{res['delta_nll']:+.5f} | {res['baseline']['top1']:.3f} | {res['variant']['top1']:.3f} |")
    md.append('\n## 最終對比（逐步疊加，α=0.2）\n')
    md.append('| 配置 | NLL | Brier | Top-1 | Top-3 | ROI (SP) |\n|---|---|---|---|---|---|')
    for name, res in staged.items():
        md.append(f"| {name} | {res['nll']:.5f} | {res['brier']:.5f} | {res['top1']:.3f} | "
                  f"{res['top3']:.3f} | {fmt(res['roi_pct'], 1)}% |")
    md.append('\n## 部署決定\n')
    calib_note = ('無需校準（T=8 即 identity）' if abs(power - 1.0) < 1e-9
                  else f'P_final 前 p^(8/{calib_t}) 重正規化')
    md.append(f'- γ={gamma_deploy}（單一市場指數，分段不加乘）；P_model 校準：{calib_note}')
    md.append(f'- 融合 α={MODEL_WEIGHT} 為核心；賠率 <{EXTREME_BAND[0]} 或 >{EXTREME_BAND[1]} 時 α={EXTREME_ALPHA}')
    md.append('- 納入 P_model：form 貝氏收縮、official_rating 35% 混入 class 因子、'
              'draw_v2（實際場人數 × 場地/途程係數）')
    md.append('- 僅展示、不入 P_model：速度排名（best_time 同場同程 Z/排名，'
              '消融 +0.011/+0.032 NLL）、負磅變動（-0.001 NLL）')
    md.append('- 否決：缺值權重重正規化（avail_aware +0.021 NLL）；改為 UI 顯示「待定」缺值旗標')
    if weights_source.get('fitted_at'):
        md.append(f"- 9 維度權重：{weights_source['fitted_at']} 以 {weights_source['sample_races']} 場"
                  f"重新擬合（見 scripts/weights_active.json；修復 history 查詢前的 v5.84 表已作廢）")
    else:
        md.append('- 9 維度權重：未發佈自訂表，使用手設基線（model_config.RAW_WEIGHTS_*）')
    md.append('- 限制：真實賽前價僅 9/343 場，ROI 為 SP 上限值；'
              '權重再擬合與本回測測試段在時間上部分重疊，γ/T/α 以每折 walk-forward 選出\n')
    md_path = os.path.join(args.out_dir, f'backtest_phase12_{day}.md')
    with open(md_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(md) + '\n')
    print(f'\n[Report] {md_path}')
    print(f'[Report] {json_path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())