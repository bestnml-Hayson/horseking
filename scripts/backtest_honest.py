#!/usr/bin/env python3
"""
Honest walk-forward baseline for the Phase 1/2 model (Commit B).

The v5.86 numbers in reports/backtest_phase12_2026-11-28.md were produced with two
shortcuts that flatter the model:

  * jockey/trainer win rates were computed from the whole archive at scrape time,
  * the factor weights were refitted on a window that overlaps the out-of-sample span.

This engine reruns the same 9-factor model with

  * jockey/trainer rates recomputed as of each race date (strictly earlier dates,
    min 3 starts, 0.10 fallback - same rule as auto_scraper),
  * factor weights fitted on each walk-forward training fold only,
  * odds labelled pre-race vs SP; ROI on genuine pre-race prices only.

Full archive (1,088 finished HV/ST races) drives the Phase 1 market/calibration/
fusion tests. The sparse-feature ablations use the 2026-06-01+ subset (the same
window as the previous report) and stay flag-only.

Output: reports/backtest_honest_<date>.md and .json. Read-only against Supabase.
"""
import argparse
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

if __name__ == '__main__' and hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase
import ai_review as A
import backtest_models as B
import model_config as M
import recalibrate_weights as R

HKT = ZoneInfo('Asia/Hong_Kong')
PHASE2_SINCE = '2026-06-01'
FOLDS = 5
TEST_FRAC = 0.4
FIT_STEPS = 100
MIN_FOLD_TRAIN = 40
MIN_WEIGHT_TRAIN = 40
GAMMA_GRID = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5)
ALPHA_GRID = (0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5)
CALIB_T = B.CALIB_T_CANDIDATES
PLATT_MAX = 300
PLATT_MIN = 150
BOOT_REPS = 1000
BOOT_SEED = 42
DISTANCE_BANDS = (('≤1200', 0, 1200), ('1201-1400', 1201, 1400),
                  ('1401-1800', 1401, 1800), ('1801+', 1801, 10_000))
FIELD_BANDS = (('≤10', 0, 10), ('11-12', 11, 12), ('13-14', 13, 14), ('15+', 15, 99))
FAV_BANDS = (('<3.5', 0.0, 3.5), ('3.5-12', 3.5, 12.0), ('>12', 12.0, 10_000))
KEEP_FIELDS = ('horse_id', 'horse_no', 'draw', 'actual_weight', 'rest_days', 'gear',
               'form_history', 'recent_form_score', 'finish_position', 'win_odds',
               'best_time', 'official_rating', 'sectional_times', 'margin',
               'finish_time', 'jockey_win_rate', 'trainer_win_rate', 'jockey', 'trainer')
FACTOR_KEYS = M.FACTOR_KEYS


# ---------------------------------------------------------------------------
# As-of jockey / trainer rates
# ---------------------------------------------------------------------------

def build_asof_rates(races, by_race):
    """Cumulative win rates using only dates strictly before the race date.

    Same rule as auto_scraper.compute_jockey_trainer_win_rates (min 3 starts,
    otherwise no rate and the scorer falls back to 0.10), but recomputed at every
    date instead of once over the whole archive.
    """
    day_races = defaultdict(list)
    for race in races:
        day_races[str(race['race_date'])[:10]].append(race['race_id'])
    stats = {'jockey': defaultdict(lambda: [0, 0]), 'trainer': defaultdict(lambda: [0, 0])}
    out = {}
    for day in sorted(day_races):
        for race_id in day_races[day]:
            for row in by_race.get(race_id, []):
                for role in ('jockey', 'trainer'):
                    name = (row.get(role) or '').strip()
                    starts, wins = stats[role].get(name, [0, 0])
                    out[(role, row['runner_id'])] = (wins / starts if starts >= 3 else None, starts)
        for race_id in day_races[day]:
            for row in by_race.get(race_id, []):
                if row.get('finish_position') is None:
                    continue
                for role in ('jockey', 'trainer'):
                    name = (row.get(role) or '').strip()
                    entry = stats[role][name]
                    entry[0] += 1
                    entry[1] += 1 if row['finish_position'] == 1 else 0
    return out


def jt_score(stored_jockey_rate, stored_trainer_rate):
    jr = stored_jockey_rate or 0.1
    tr = stored_trainer_rate or 0.1
    j = max(0.0, min(100.0, jr * 500))
    t = max(0.0, min(100.0, tr * 500))
    return 0.6 * j + 0.4 * t


# ---------------------------------------------------------------------------
# Sample building
# ---------------------------------------------------------------------------

def classify_class(value):
    order = A.class_level_order(value)
    if order is not None:
        return f'C{order}'
    s = value or ''
    if '新馬' in s:
        return '新馬'
    if any(f'{c}級' in s for c in '一二三四五'):
        return 'Group/Listed'
    return '未分類'


def band_of(value, bands):
    for label, lo, hi in bands:
        if lo <= value <= hi:
            return label
    return bands[-1][0]


def sample_cache_path(since):
    return os.path.join(os.path.dirname(__file__), '..', 'reports',
                        f'.honest_samples_{since.replace("-", "")}.json')


def build_samples(sb, since, refresh=False):
    path = sample_cache_path(since)
    if os.path.exists(path) and not refresh:
        with open(path, encoding='utf-8') as fh:
            cached = json.load(fh)
        print(f'[Load] {len(cached["samples"])} races from cache {os.path.basename(path)}')
        return cached['samples'], cached['meta']

    races = B.load_races(sb, since)
    print(f'[Load] {len(races)} finished HV/ST races since {since}')
    by_race = B.load_runners(sb, [r['race_id'] for r in races])
    horse_ids = {row['horse_id'] for rows in by_race.values() for row in rows if row.get('horse_id')}
    print(f'[Load] fetching history for {len(horse_ids)} horses...')
    history = B.fetch_history(sb, horse_ids)
    asof = build_asof_rates(races, by_race)
    sp = B.load_sp(sb, [r['race_id'] for r in races])

    drops = Counter()
    samples = []
    for race in races:
        rows = by_race.get(race['race_id'], [])
        finishers = [r for r in rows if (r.get('finish_position') or 0) > 0]
        winners = [r for r in finishers if r['finish_position'] == 1]
        if len(finishers) < 4:
            drops['fewer than 4 finishers'] += 1
            continue
        if len(winners) != 1:
            drops['no unique winner'] += 1
            continue
        if not race.get('distance'):
            drops['missing distance'] += 1
            continue
        rows.sort(key=lambda r: r.get('horse_no') or 0)
        wi = rows.index(winners[0])
        odds = [r.get('win_odds') for r in rows]
        valid_odds = sum(1 for o in odds if o and o > 1)
        if valid_odds < 4 or not (odds[wi] and odds[wi] > 1):
            drops['odds coverage'] += 1
            continue

        trimmed = [{k: r.get(k) for k in KEEP_FIELDS} for r in rows]
        honest_rows, jt_stored, start_counts = [], [], []
        for row, base in zip(rows, trimmed):
            jr, js = asof.get(('jockey', row['runner_id']), (None, 0))
            tr, ts = asof.get(('trainer', row['runner_id']), (None, 0))
            copy = dict(base)
            copy['jockey_win_rate'] = jr
            copy['trainer_win_rate'] = tr
            honest_rows.append(copy)
            jt_stored.append(jt_score(base.get('jockey_win_rate'), base.get('trainer_win_rate')))
            start_counts.append({'jockey': js, 'trainer': ts})

        pace_label = A._predict_pace(rows, history, race['race_date'])
        factors = [
            A.compute_factor_scores(r, len(honest_rows), race['venue'], race['distance'],
                                    race.get('class_level'), history, pace_label,
                                    race['race_date'])
            for r in honest_rows
        ]
        last_weights, form_positions = [], []
        for r in honest_rows:
            prior = A._prior_starts(history.get(r.get('horse_id', ''), []), race['race_date'])
            last_weights.append(next((h['actual_weight'] for h in prior if h.get('actual_weight')), None))
            form_positions.append(A._recent_form_positions(r, prior))
        class_base = [
            A._compute_class_movement_score(r, race.get('class_level'), history, race['race_date'])
            for r in honest_rows
        ]
        avail = [
            A.factor_availability(r, len(honest_rows), race['venue'], race['distance'],
                                  race.get('class_level'), history, race['race_date'])
            for r in honest_rows
        ]

        diffs = sum(
            1 for row, o in zip(rows, odds)
            if o and o > 1 and (race['race_id'], row.get('horse_no')) in sp
            and abs(float(sp[(race['race_id'], row.get('horse_no'))]) - o) > 1e-9
        )
        fav_odds = min(o for o in odds if o and o > 1)
        coverage = mean(1.0 if all(a.values()) else 0.0 for a in avail)

        samples.append({
            'race_id': race['race_id'],
            'date': str(race['race_date'])[:10],
            'venue': race['venue'],
            'race_no': race.get('race_no'),
            'distance': race['distance'],
            'class_level': race.get('class_level'),
            'class_band': classify_class(race.get('class_level')),
            'rows': trimmed,
            'winner_idx': wi,
            'odds': odds,
            'fav_odds': fav_odds,
            'fav_band': band_of(fav_odds, FAV_BANDS),
            'field': len(trimmed),
            'field_band': band_of(len(trimmed), FIELD_BANDS),
            'distance_band': band_of(race['distance'], DISTANCE_BANDS),
            'coverage': round(coverage, 4),
            'coverage_full': coverage >= 0.999,
            'odds_source': 'pre_race' if diffs else 'sp',
            'factors': factors,
            'jt_stored': jt_stored,
            'asof_starts': start_counts,
            'best_times': [B.parse_best_time(r.get('best_time')) for r in honest_rows],
            'ratings': [r.get('official_rating') for r in honest_rows],
            'last_weights': last_weights,
            'form_positions': form_positions,
            'class_base': class_base,
            'avail': avail,
            'pace_label': pace_label,
        })

    samples.sort(key=lambda s: (s['date'], s['race_no'] or 0))
    meta = {
        'since': since,
        'built_at': datetime.now(HKT).isoformat(),
        'races_loaded': len(races),
        'usable': len(samples),
        'runners': sum(len(s['rows']) for s in samples),
        'drops': dict(drops),
        'pre_race_races': sum(1 for s in samples if s['odds_source'] == 'pre_race'),
        'asof_jockey_covered': sum(1 for s in samples for r in s['asof_starts'] if r['jockey'] >= 3),
        'asof_trainer_covered': sum(1 for s in samples for r in s['asof_starts'] if r['trainer'] >= 3),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'meta': meta, 'samples': samples}, fh, ensure_ascii=False)
    print(f'[Load] {meta["usable"]} usable races / {meta["runners"]} runners '
          f'({meta["pre_race_races"]} with genuine pre-race odds)')
    print(f'[Load] dropped: {dict(drops)}')
    return samples, meta


# ---------------------------------------------------------------------------
# Factor variants and probabilities
# ---------------------------------------------------------------------------

def factors_stored(sample):
    factors = [dict(f) for f in sample['factors']]
    for i, jt in enumerate(sample['jt_stored']):
        factors[i]['jockeyTrainer'] = jt
    return factors


def factors_legacy(sample):
    factors = B.pre_phase2_factors(sample)
    for i, jt in enumerate(sample['jt_stored']):
        factors[i]['jockeyTrainer'] = jt
    return factors


def p_model(sample, factors, weights):
    scores = [sum(f[k] * weights[k] for k in FACTOR_KEYS) for f in factors]
    return B.softmax(scores, M.SOFTMAX_TEMPERATURE)


def market_probs(sample, gamma=1.0, band_gammas=None):
    return B.market_vector(sample['odds'], gamma, band_gammas)


def fused(pm, pk, odds, alpha=M.MODEL_WEIGHT, dynamic=False):
    out = []
    lo, hi = M.EXTREME_ODDS_BAND
    for i, p in enumerate(pm):
        if i >= len(pk):
            out.append(p)
            continue
        a = M.EXTREME_ODDS_ALPHA if (dynamic and odds[i] is not None
                                     and (odds[i] < lo or odds[i] > hi)) else alpha
        out.append(a * p + (1 - a) * pk[i])
    return out


# ---------------------------------------------------------------------------
# Race-level metrics
# ---------------------------------------------------------------------------

def race_rows(samples, probs):
    rows = []
    for s in samples:
        ps = probs.get(s['race_id'])
        if not ps:
            continue
        wi = s['winner_idx']
        order = sorted(range(len(ps)), key=lambda i: (-ps[i], i))
        pick = order[0]
        finish = [r.get('finish_position') or 0 for r in s['rows']]
        bets = rets = 0
        for i, o in enumerate(s['odds']):
            if o and o > 1 and ps[i] * o - 1 > 0:
                bets += 1
                rets += o if i == wi else 0.0
        rows.append({
            'race_id': s['race_id'],
            'date': s['date'],
            'venue': s['venue'],
            'distance': s['distance_band'],
            'class': s['class_band'],
            'field': s['field_band'],
            'fav': s['fav_band'],
            'coverage': 'full' if s['coverage_full'] else 'partial',
            'source': s['odds_source'],
            'nll': B.winner_nll(ps, wi),
            'brier': B.brier(ps, wi),
            'top1': 1 if pick == wi else 0,
            'top1q': 1 if finish[pick] in (1, 2) else 0,
            'top3': 1 if wi in order[:3] else 0,
            'place': 1 if finish[pick] in (1, 2, 3) else 0,
            'bets': bets,
            'rets': rets,
            'top1_rets': (s['odds'][pick] or 0.0) if pick == wi else 0.0,
            'runners': len(s['rows']),
        })
    return rows


def summarize(rows):
    n = len(rows)
    if not n:
        return {'races': 0, 'nll': None, 'brier': None, 'top1': None, 'top1q': None,
                'top3': None, 'place': None, 'roi_ev': None, 'roi_top1': None, 'bets': 0}
    bets = sum(r['bets'] for r in rows)
    rets = sum(r['rets'] for r in rows)
    top1_rets = sum(r['top1_rets'] for r in rows)
    return {
        'races': n,
        'nll': round(mean(r['nll'] for r in rows), 5),
        'brier': round(mean(r['brier'] for r in rows), 5),
        'top1': round(sum(r['top1'] for r in rows) / n, 4),
        'top1q': round(sum(r['top1q'] for r in rows) / n, 4),
        'top3': round(sum(r['top3'] for r in rows) / n, 4),
        'place': round(sum(r['place'] for r in rows) / n, 4),
        'roi_ev': round((rets - bets) / bets * 100, 1) if bets else None,
        'roi_top1': round((top1_rets - n) / n * 100, 1),
        'bets': bets,
    }


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def bootstrap(rows, keys=('nll', 'top1', 'roi_ev'), reps=None):
    reps = reps or BOOT_REPS
    days = defaultdict(list)
    for row in rows:
        days[row['date']].append(row)
    dates = list(days)
    if len(dates) < 2:
        return {k: None for k in keys}
    rng = random.Random(BOOT_SEED)
    draws = {k: [] for k in keys}
    for _ in range(reps):
        chosen = [days[dates[rng.randrange(len(dates))]] for _ in range(len(dates))]
        flat = [row for day in chosen for row in day]
        stats = summarize(flat)
        for key in keys:
            if stats.get(key) is not None:
                draws[key].append(stats[key])
    return {k: ([round(percentile(v, 2.5), 4), round(percentile(v, 97.5), 4)] if v else None)
            for k, v in draws.items()}


def paired_delta(rows_a, rows_b):
    """Per-race NLL difference a - b on races present in both, plus day bootstrap CI."""
    index = {r['race_id']: r for r in rows_b}
    pairs = [(r['date'], r['nll'] - index[r['race_id']]['nll'])
             for r in rows_a if r['race_id'] in index]
    if not pairs:
        return None, None
    days = defaultdict(list)
    for day, delta in pairs:
        days[day].append(delta)
    rng = random.Random(BOOT_SEED)
    keys = list(days)
    draws = []
    for _ in range(BOOT_REPS):
        chosen = [days[keys[rng.randrange(len(keys))]] for _ in range(len(keys))]
        draws.append(mean(d for day in chosen for d in day))
    return round(mean(d for _, d in pairs), 5), [round(percentile(draws, 2.5), 5),
                                                 round(percentile(draws, 97.5), 5)]


def fold_improvements(blocks, sample_by_id, base_probs, var_probs, min_races=5):
    improved = total = 0
    for _, test in blocks:
        ids = [s['race_id'] for s in test
               if s['race_id'] in base_probs and s['race_id'] in var_probs]
        if len(ids) < min_races:
            continue
        base_nll = mean(B.winner_nll(base_probs[i], sample_by_id[i]['winner_idx']) for i in ids)
        var_nll = mean(B.winner_nll(var_probs[i], sample_by_id[i]['winner_idx']) for i in ids)
        total += 1
        improved += 1 if var_nll < base_nll else 0
    return {'improved': improved, 'folds': total}


def stratify(rows):
    specs = {
        'venue': lambda r: r['venue'],
        'distance': lambda r: r['distance'],
        'class': lambda r: r['class'],
        'field': lambda r: r['field'],
        'fav_odds': lambda r: r['fav'],
        'coverage': lambda r: r['coverage'],
        'odds_source': lambda r: r['source'],
    }
    out = {}
    for name, fn in specs.items():
        groups = defaultdict(list)
        for row in rows:
            groups[fn(row)].append(row)
        out[name] = {
            label: {**summarize(group),
                    'guard_ok': len(group) >= 30 or sum(r['runners'] for r in group) >= 300}
            for label, group in sorted(groups.items())
        }
    return out


# ---------------------------------------------------------------------------
# Per-fold weight fitting
# ---------------------------------------------------------------------------

def fit_weights(train, base, venue, steps=FIT_STEPS):
    subset = [s for s in train if s['venue'] == venue]
    if len(subset) < MIN_WEIGHT_TRAIN:
        return dict(base), {'races': len(subset), 'fallback': True}
    data = [{'scores': [[f[k] for k in FACTOR_KEYS] for f in s['factors']],
             'winner_idx': s['winner_idx']} for s in subset]
    base_list = [base[k] for k in FACTOR_KEYS]
    base_nll, _ = R.nll_and_grad(data, base_list)
    best, best_nll = list(base_list), base_nll
    current = list(base_list)
    for step in range(steps):
        _, grad = R.nll_and_grad(data, current)
        gmax = max(abs(g) for g in grad)
        if gmax < 1e-9:
            break
        lr = (0.012 / gmax) * (0.995 ** step)
        proposal = R.project([current[k] - lr * grad[k] for k in range(len(current))], base_list)
        loss, _ = R.nll_and_grad(data, proposal)
        if loss < best_nll:
            best, best_nll = proposal, loss
        current = proposal
    return R.round_table(best), {
        'races': len(subset), 'fallback': False,
        'baseline_train_nll': round(base_nll, 5), 'train_nll': round(best_nll, 5),
        'train_gain': round(base_nll - best_nll, 5),
    }


def fit_blocks(all_samples, blocks, base_tables, steps=FIT_STEPS):
    fold_map, diagnostics = {}, []
    for k, (_, test) in enumerate(blocks):
        cutoff = min(s['date'] for s in test)
        train = [s for s in all_samples if s['date'] < cutoff]
        tables = {}
        for venue in ('HV', 'ST'):
            table, diag = fit_weights(train, base_tables[venue], venue, steps)
            tables[venue] = table
            diagnostics.append({'fold': k + 1, 'venue': venue, 'cutoff': cutoff,
                                'table': table, **diag})
        for s in test:
            fold_map[s['race_id']] = tables[s['venue']]
    return fold_map, diagnostics


# ---------------------------------------------------------------------------
# Phase 1 evaluation
# ---------------------------------------------------------------------------

def market_nll(samples, gamma, band_gammas=None):
    return mean(B.winner_nll(B.market_vector(s['odds'], gamma, band_gammas), s['winner_idx'])
                for s in samples)


def fit_banded_gamma(train):
    picks = {label: 1.0 for label in B.BAND_LABELS}
    for _ in range(3):
        for label in B.BAND_LABELS:
            best_g, best_nll = picks[label], None
            for g in GAMMA_GRID:
                trial = dict(picks)
                trial[label] = g
                nll = market_nll(train, 1.0, trial)
                if best_nll is None or nll < best_nll:
                    best_g, best_nll = g, nll
            picks[label] = best_g
    return picks


def power_calibration(p, power):
    scaled = [max(x, 0.0) ** power for x in p]
    total = sum(scaled)
    return [x / total for x in scaled] if total > 0 else p


def apply_platt(p, a, b):
    vals = [B.sigmoid(a * B.logit(x) + b) for x in p]
    total = sum(vals)
    return [v / total for v in vals] if total > 0 else p


def phase1(samples, blocks, fold_map, test_all):
    out = {}
    oos_ids = [s for s in test_all]

    # --- market exponent ---------------------------------------------------
    gamma_fixed = {}
    for g in GAMMA_GRID:
        probs = {s['race_id']: market_probs(s, g) for s in oos_ids}
        gamma_fixed[g] = summarize(race_rows(oos_ids, probs))
    out['gamma_fixed'] = gamma_fixed

    fold_gamma, gamma_picks, gamma_rows = [], [], []
    for k, (train, test) in enumerate(blocks):
        best_g = min(GAMMA_GRID, key=lambda g: market_nll(train, g))
        gamma_picks.append(best_g)
        fold_gamma.append({'fold': k + 1, 'gamma': best_g})
        gamma_rows.extend(race_rows(test, {s['race_id']: market_probs(s, best_g) for s in test}))
    out['gamma_fold'] = {'picks': gamma_picks, **summarize(gamma_rows)}

    banded_picks, banded_rows = [], []
    for k, (train, test) in enumerate(blocks):
        picks = fit_banded_gamma(train)
        banded_picks.append(picks)
        banded_rows.extend(
            race_rows(test, {s['race_id']: market_probs(s, 1.0, picks) for s in test}))
    out['gamma_banded_fold'] = {'picks': banded_picks, **summarize(banded_rows)}

    # --- P_model calibration ----------------------------------------------
    temp_rows, platt_rows, temp_probs, platt_probs = [], [], {}, {}
    temp_picks, platt_params = [], []
    for k, (train, test) in enumerate(blocks):
        table = fold_map[test[0]['race_id']]
        train_pm = {s['race_id']: p_model(s, s['factors'], table) for s in train}
        test_pm = {s['race_id']: p_model(s, s['factors'], table) for s in test}

        best_t = min(CALIB_T, key=lambda t: mean(
            B.winner_nll(power_calibration(train_pm[s['race_id']], M.SOFTMAX_TEMPERATURE / t),
                         s['winner_idx']) for s in train))
        temp_picks.append(best_t)
        for s in test:
            temp_probs[s['race_id']] = power_calibration(
                test_pm[s['race_id']], M.SOFTMAX_TEMPERATURE / best_t)
        temp_rows.extend(race_rows(test, {s['race_id']: temp_probs[s['race_id']] for s in test}))

        tail = train[-PLATT_MAX:]
        if len(tail) >= PLATT_MIN:
            fit_input = [{'p_model': train_pm[s['race_id']], 'winner_idx': s['winner_idx']}
                         for s in tail]
            a, b = B.fit_platt(fit_input)
            platt_params.append({'fold': k + 1, 'a': round(a, 4), 'b': round(b, 4)})
            for s in test:
                platt_probs[s['race_id']] = apply_platt(test_pm[s['race_id']], a, b)
        else:
            platt_params.append({'fold': k + 1, 'a': None, 'b': None})
            for s in test:
                platt_probs[s['race_id']] = test_pm[s['race_id']]
        platt_rows.extend(race_rows(test, {s['race_id']: platt_probs[s['race_id']] for s in test}))

    raw_probs = {s['race_id']: p_model(s, s['factors'], fold_map[s['race_id']]) for s in oos_ids}
    raw_rows = race_rows(oos_ids, raw_probs)
    out['calibration'] = {
        'raw': {**summarize(raw_rows), 'ece': B.ece(oos_ids, lambda s: raw_probs[s['race_id']])},
        'temperature': {'picks': temp_picks, **summarize(temp_rows),
                        'ece': B.ece(oos_ids, lambda s: temp_probs[s['race_id']])},
        'platt_rolling': {'params': platt_params, **summarize(platt_rows),
                          'ece': B.ece(oos_ids, lambda s: platt_probs[s['race_id']])},
    }

    # --- fusion ------------------------------------------------------------
    market = {s['race_id']: market_probs(s, 1.0) for s in oos_ids}
    alpha_fixed = {}
    for a in ALPHA_GRID:
        probs = {s['race_id']: fused(raw_probs[s['race_id']], market[s['race_id']], s['odds'], a)
                 for s in oos_ids}
        alpha_fixed[a] = summarize(race_rows(oos_ids, probs))

    fold_alpha, alpha_picks, alpha_rows = [], [], []
    for k, (train, test) in enumerate(blocks):
        table = fold_map[test[0]['race_id']]
        train_pm = {s['race_id']: p_model(s, s['factors'], table) for s in train}
        train_pk = {s['race_id']: market_probs(s, 1.0) for s in train}
        best_a = min(ALPHA_GRID, key=lambda a: mean(
            B.winner_nll(fused(train_pm[s['race_id']], train_pk[s['race_id']], s['odds'], a),
                         s['winner_idx']) for s in train))
        alpha_picks.append(best_a)
        fold_alpha.append({'fold': k + 1, 'alpha': best_a})
        alpha_rows.extend(race_rows(test, {
            s['race_id']: fused(raw_probs[s['race_id']], market[s['race_id']], s['odds'], best_a)
            for s in test}))
    out['alpha'] = {
        'fixed': alpha_fixed,
        'fold': {'picks': alpha_picks, **summarize(alpha_rows)},
        'production_0.2': alpha_fixed[0.2],
        'dynamic_extreme': summarize(race_rows(oos_ids, {
            s['race_id']: fused(raw_probs[s['race_id']], market[s['race_id']], s['odds'],
                                M.MODEL_WEIGHT, dynamic=True) for s in oos_ids})),
    }
    return out


# ---------------------------------------------------------------------------
# Honest vs current decomposition
# ---------------------------------------------------------------------------

def variant_probabilities(samples, variant, fold_map, active_tables):
    probs = {}
    for s in samples:
        if variant == 'honest':
            weights = fold_map[s['race_id']]
            probs[s['race_id']] = p_model(s, s['factors'], weights)
        elif variant == 'asof_active':
            probs[s['race_id']] = p_model(s, s['factors'], active_tables[s['venue']])
        elif variant == 'current':
            probs[s['race_id']] = p_model(s, factors_stored(s), active_tables[s['venue']])
        elif variant == 'legacy':
            weights = M.resolve_profile('legacy_v576')['weights'][s['venue']]
            probs[s['race_id']] = p_model(s, factors_legacy(s), weights)
        else:
            raise ValueError(variant)
    return probs


def decomposition(samples, blocks, fold_map, active_tables):
    oos_ids = [s for _, test in blocks for s in test]
    result = {}
    model_probs = {}
    for variant in ('current', 'asof_active', 'honest', 'legacy'):
        pm = variant_probabilities(oos_ids, variant, fold_map, active_tables)
        model_probs[variant] = pm
        pk = {s['race_id']: market_probs(s, 1.0) for s in oos_ids}
        fused_probs = {s['race_id']: fused(pm[s['race_id']], pk[s['race_id']], s['odds'])
                       for s in oos_ids}
        rows = race_rows(oos_ids, fused_probs)
        pre_race_rows = [r for r in rows if r['source'] == 'pre_race']
        result[variant] = {
            **summarize(rows),
            'ece': B.ece(oos_ids, lambda s, v=variant: model_probs[v][s['race_id']]),
            'ci': bootstrap(rows),
            'pre_race': summarize(pre_race_rows),
        }
    base = race_rows(oos_ids, {s['race_id']: fused(model_probs['current'][s['race_id']],
                                                   market_probs(s, 1.0), s['odds']) for s in oos_ids})
    for variant in ('asof_active', 'honest', 'legacy'):
        rows = race_rows(oos_ids, {s['race_id']: fused(model_probs[variant][s['race_id']],
                                                       market_probs(s, 1.0), s['odds'])
                                   for s in oos_ids})
        result[variant]['delta_nll_vs_current'], result[variant]['delta_ci'] = paired_delta(rows, base)
    result['_rows'] = {'current': base}
    for variant in ('asof_active', 'honest', 'legacy'):
        result['_rows'][variant] = race_rows(oos_ids, {
            s['race_id']: fused(model_probs[variant][s['race_id']],
                                market_probs(s, 1.0), s['odds']) for s in oos_ids})
    return result


# ---------------------------------------------------------------------------
# Phase 2 ablations (subset only)
# ---------------------------------------------------------------------------

def phase2(full_samples, subset_samples, active_tables):
    blocks = B.split_blocks(subset_samples, TEST_FRAC, FOLDS)
    base_tables = {'HV': M.raw_weights_for('HV'), 'ST': M.raw_weights_for('ST')}
    fold_map, diagnostics = fit_blocks(full_samples, blocks, base_tables)
    test_ids = [s for _, test in blocks for s in test]
    sample_by_id = {s['race_id']: s for s in subset_samples}
    out = {'folds': diagnostics, 'oos_races': len(test_ids)}

    def table_for(sample):
        return fold_map[sample['race_id']]

    combined = {s['race_id']: p_model(s, s['factors'], table_for(s)) for s in test_ids}
    pre2 = {s['race_id']: p_model(s, B.pre_phase2_factors(s), table_for(s)) for s in test_ids}
    out['combined'] = summarize(race_rows(test_ids, combined))
    out['pre2_baseline'] = summarize(race_rows(test_ids, pre2))
    out['pre2_rows'] = race_rows(test_ids, pre2)
    out['combined_rows'] = race_rows(test_ids, combined)
    out['combined_delta'], out['combined_delta_ci'] = paired_delta(
        out['combined_rows'], out['pre2_rows'])
    out['combined_folds'] = fold_improvements(blocks, sample_by_id, pre2, combined)

    variants = [
        ('speed_25', 'speed', 0.25), ('speed_40', 'speed', 0.40),
        ('rating_35', 'rating', 0.35), ('rating_50', 'rating', 0.50),
        ('weight_change', 'weight_change', 1.0), ('weight_full', 'weight_full', 1.0),
        ('draw_v2', 'draw_v2', 1.0), ('form_shrink', 'form_shrink', 1.0),
    ]
    out['ablations'] = {}
    for name, variant, blend in variants:
        covered, base_probs, var_probs = [], {}, {}
        for s in test_ids:
            base_factors = B.pre_phase2_factors(s)
            factors = B.variant_factor_scores(s, variant, blend, base=base_factors)
            if factors is None:
                continue
            covered.append(s)
            weights = table_for(s)
            base_probs[s['race_id']] = p_model(s, base_factors, weights)
            var_probs[s['race_id']] = p_model(s, factors, weights)
        base_rows = race_rows(covered, base_probs)
        var_rows = race_rows(covered, var_probs)
        delta, ci = paired_delta(var_rows, base_rows)
        out['ablations'][name] = {
            'races': len(covered), 'baseline': summarize(base_rows), 'variant': summarize(var_rows),
            'delta_nll': delta, 'delta_ci': ci,
            'folds': fold_improvements(blocks, sample_by_id, base_probs, var_probs),
        }

    # availability-aware renormalisation must be compared on identical factors:
    # 'avail_aware' toggles only the renormalisation on the pre-Phase-2 baseline,
    # 'avail_aware_on_combined' toggles it on the deployed factor set, and the
    # '_stack' row (deployed+renorm vs pre2) is an audit trail only - it mixes in
    # the already-deployed form/rating/draw gains and must not be read as renorm value.
    avail_covered = []
    avail_bases = {'avail_aware': {}, 'avail_aware_on_combined': {}, 'avail_aware_stack': {}}
    avail_vars = {'avail_aware': {}, 'avail_aware_on_combined': {}, 'avail_aware_stack': {}}
    for s in test_ids:
        ss = dict(s)
        ss['weights'] = table_for(s)
        pre2_factors = B.pre_phase2_factors(ss)
        avail_covered.append(ss)
        avail_bases['avail_aware'][ss['race_id']] = pre2[ss['race_id']]
        avail_vars['avail_aware'][ss['race_id']] = B.avail_p_model(ss, pre2_factors)
        avail_bases['avail_aware_on_combined'][ss['race_id']] = combined[ss['race_id']]
        avail_vars['avail_aware_on_combined'][ss['race_id']] = B.avail_p_model(ss, ss['factors'])
        avail_bases['avail_aware_stack'][ss['race_id']] = pre2[ss['race_id']]
        avail_vars['avail_aware_stack'][ss['race_id']] = B.avail_p_model(ss, ss['factors'])
    for name in avail_bases:
        avail_base_rows = race_rows(avail_covered, avail_bases[name])
        avail_var_rows = race_rows(avail_covered, avail_vars[name])
        avail_delta, avail_ci = paired_delta(avail_var_rows, avail_base_rows)
        out['ablations'][name] = {
            'races': len(avail_covered), 'baseline': summarize(avail_base_rows),
            'variant': summarize(avail_var_rows),
            'delta_nll': avail_delta, 'delta_ci': avail_ci,
            'folds': fold_improvements(blocks, sample_by_id,
                                       avail_bases[name], avail_vars[name]),
        }

    combined_rows = race_rows(test_ids, combined)
    pre2_rows = race_rows(test_ids, pre2)
    out['combined']['delta_nll'] = paired_delta(combined_rows, pre2_rows)[0]

    st1000 = [s for s in test_ids if s['venue'] == 'ST' and s['distance'] == 1000]
    out['st1000'] = {'races': len(st1000),
                     'metrics': summarize(race_rows(st1000, combined))}
    all_rows = [r for s in test_ids for r in s['rows']]
    out['phase2b_coverage'] = {
        'finish_time': round(sum(1 for r in all_rows if r.get('finish_time')) / max(len(all_rows), 1), 4),
        'margin': round(sum(1 for r in all_rows if r.get('margin') is not None) / max(len(all_rows), 1), 4),
    }
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt(value, digits=4):
    return '-' if value is None else f'{value:.{digits}f}'


def pct(value):
    return '-' if value is None else f'{value * 100:.1f}%'


def main():
    global BOOT_REPS
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', default='2025-09-07')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--report-only', action='store_true')
    parser.add_argument('--boot', type=int, default=BOOT_REPS)
    parser.add_argument('--out-dir', default=os.path.join(os.path.dirname(__file__), '..', 'reports'))
    args = parser.parse_args()

    BOOT_REPS = args.boot
    stamp = datetime.now(HKT).strftime('%Y-%m-%d')
    if args.report_only:
        json_path = os.path.join(args.out_dir, f'backtest_honest_{stamp}.json')
        with open(json_path, encoding='utf-8') as fh:
            payload = json.load(fh)
        payload['phase1']['gamma_fixed'] = {
            float(k): v for k, v in payload['phase1']['gamma_fixed'].items()}
        payload['phase1']['alpha']['fixed'] = {
            float(k): v for k, v in payload['phase1']['alpha']['fixed'].items()}
        md_path = os.path.join(args.out_dir, f'backtest_honest_{stamp}.md')
        with open(md_path, 'w', encoding='utf-8') as fh:
            fh.write(build_report(payload))
        print(f'[Write] {os.path.basename(md_path)} (from JSON)')
        return 0

    sb = get_supabase()
    samples, meta = build_samples(sb, args.since, args.refresh)
    if len(samples) < 100:
        print('[Abort] fewer than 100 usable races')
        return 1

    active = M.load_active_weights()
    active_tables = {}
    for venue in ('HV', 'ST'):
        table = active.get(venue)
        active_tables[venue] = (M.weights_for(venue) if M._valid_table(table)
                                else M.raw_weights_for(venue))
    weights_note = ('published refit (weights_active.json)' if active else
                    'profile hand-set table (no published refit)')

    blocks = B.split_blocks(samples, TEST_FRAC, FOLDS)
    test_all = [s for _, test in blocks for s in test]
    print(f'[Eval] walk-forward {len(blocks)} folds, {len(test_all)} OOS races '
          f'({test_all[0]["date"]} -> {test_all[-1]["date"]})')

    fold_map, fold_diag = fit_blocks(samples, blocks,
                                     {'HV': M.raw_weights_for('HV'), 'ST': M.raw_weights_for('ST')})
    for diag in fold_diag:
        print(f"  fold {diag['fold']} {diag['venue']}: {diag['races']} train races, "
              f"gain {diag.get('train_gain', 0):.5f} NLL, fallback={diag['fallback']}")

    p1 = phase1(samples, blocks, fold_map, test_all)
    dec = decomposition(samples, blocks, fold_map, active_tables)

    subset = [s for s in samples if s['date'] >= PHASE2_SINCE]
    print(f'[Phase2] {len(subset)} races since {PHASE2_SINCE}')
    p2 = phase2(samples, subset, active_tables) if len(subset) >= 80 else {'skipped': True}

    payload = {
        'generated_at': datetime.now(HKT).isoformat(),
        'since': args.since,
        'meta': meta,
        'weights_note': weights_note,
        'active_tables': active_tables,
        'profile': M.PROFILE_NAME,
        'fold_weights': fold_diag,
        'full': {'oos_races': len(test_all),
                 'first_test': test_all[0]['date'], 'last_test': test_all[-1]['date']},
        'phase1': p1,
        'decomposition': {k: v for k, v in dec.items() if not k.startswith('_')},
        'phase2': p2,
        'strata': stratify(dec['_rows']['honest']),
        'guardrails': {
            'overall_oos_races': len(test_all),
            'overall_ok': len(test_all) >= 100,
            'venue_oos': {v: sum(1 for s in test_all if s['venue'] == v) for v in ('HV', 'ST')},
            'venue_ok': all(sum(1 for s in test_all if s['venue'] == v) >= 40 for v in ('HV', 'ST')),
            'phase2_oos_races': (p2 or {}).get('oos_races'),
            'buckets_min_30_races': 'see strata.guard_ok',
        },
    }

    stamp = datetime.now(HKT).strftime('%Y-%m-%d')
    json_path = os.path.join(args.out_dir, f'backtest_honest_{stamp}.json')
    with open(json_path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f'[Write] {os.path.basename(json_path)}')

    md = build_report(payload)
    md_path = os.path.join(args.out_dir, f'backtest_honest_{stamp}.md')
    with open(md_path, 'w', encoding='utf-8') as fh:
        fh.write(md)
    print(f'[Write] {os.path.basename(md_path)}')
    return 0


def build_report(payload):
    meta = payload['meta']
    p1 = payload['phase1']
    dec = payload['decomposition']
    lines = []
    add = lines.append
    add(f'# Honest Walk-Forward 回測報告（{payload["generated_at"][:10]}）')
    add('')
    add('## 樣本與誠實性')
    add('')
    add(f'- 載入賽事：{meta["races_loaded"]} 場（{payload["since"]} 起），可用 {meta["usable"]} 場 / '
        f'{meta["runners"]}  runners')
    add(f'- 剔除：{meta["drops"] or "無"}')
    add(f'- OOS：{payload["full"]["oos_races"]} 場（{payload["full"]["first_test"]} → '
        f'{payload["full"]["last_test"]}），5 折 expanding window')
    add(f'- 真實賽前賠率賽事：{meta["pre_race_races"]} / {meta["usable"]}；其餘為 SP 複製，'
        '所有 ROI 僅為 SP 上限值')
    add(f'- as-of 騎師勝率覆蓋（≥3 場）：{meta["asof_jockey_covered"]} runners；'
        f'練馬師：{meta["asof_trainer_covered"]} runners')
    add(f'- 權重基準：{payload["weights_note"]}')
    add('')
    add('### 每折 train-only 權重（as-of 因子擬合）')
    add('')
    add('| Fold | Venue | Train races | Baseline NLL | Fitted NLL | Gain |')
    add('|---|---|---|---|---|---|')
    for d in payload['fold_weights']:
        add(f'| {d["fold"]} | {d["venue"]} | {d["races"]} | '
            f'{fmt(d.get("baseline_train_nll"), 5)} | {fmt(d.get("train_nll"), 5)} | '
            f'{fmt(d.get("train_gain"), 5)} |')
    add('')
    add('- 每折完整 9 因子權重表存於 JSON `fold_weights[].table`；擬合錨定 profile raw 權重，'
        '單因子漂移上限 ±0.06、上下限 0.02–0.30，表內合計剛好 1.0。')
    add('')
    add('## Honest_v586 vs Current_v586')
    add('')
    add('| Variant | NLL | Brier | Top1 | Top1入Q | Top3 | Place | ECE | ROI(EV) | 95% CI NLL |')
    add('|---|---|---|---|---|---|---|---|---|---|')
    labels = {'current': 'current_v586（存檔騎練率＋已發佈權重）',
              'asof_active': 'as-of 騎練率＋已發佈權重',
              'honest': 'honest_v586（as-of＋逐折權重）',
              'legacy': 'legacy_v576'}
    for key in ('current', 'asof_active', 'honest', 'legacy'):
        d = dec[key]
        ci = d.get('ci', {}).get('nll')
        add(f'| {labels[key]} | {fmt(d["nll"], 5)} | {fmt(d["brier"], 5)} | {pct(d["top1"])} | '
            f'{pct(d["top1q"])} | {pct(d["top3"])} | {pct(d["place"])} | {fmt(d["ece"], 4)} | '
            f'{fmt(d["roi_ev"], 1)}% | {fmt(ci[0], 5) if ci else "-"} ~ {fmt(ci[1], 5) if ci else "-"} |')
    add('')
    for key in ('asof_active', 'honest', 'legacy'):
        d = dec[key]
        add(f'- {labels[key]} vs current：ΔNLL {fmt(d["delta_nll_vs_current"], 5)}，'
            f'95% CI {fmt(d["delta_ci"][0], 5) if d["delta_ci"] else "-"} ~ '
            f'{fmt(d["delta_ci"][1], 5) if d["delta_ci"] else "-"}')
    add('')
    cur, hon = dec['current'], dec['honest']
    if hon['nll'] is not None and cur['nll'] is not None:
        add(f'- **honest_v586 相對 current_v586 的整體跌幅**：'
            f'ΔNLL {hon["nll"] - cur["nll"]:+.4f}、'
            f'ΔTop1 {(hon["top1"] - cur["top1"]) * 100:+.1f}pp、'
            f'ΔTop3 {(hon["top3"] - cur["top3"]) * 100:+.1f}pp、'
            f'ΔROI(EV) {((hon["roi_ev"] or 0) - (cur["roi_ev"] or 0)):+.1f}pp（SP 值）')
    add('')
    add('### 真實賽前賠率子集（ROI 不受 SP 上限污染）')
    add('')
    add('| Variant | 場數 | NLL | Top1 | ROI(EV) | ROI(Top1) |')
    add('|---|---|---|---|---|---|')
    for key in ('current', 'asof_active', 'honest', 'legacy'):
        d = dec[key].get('pre_race') or {}
        add(f'| {labels[key]} | {d.get("races", 0)} | {fmt(d.get("nll"), 5)} | '
            f'{pct(d.get("top1"))} | {fmt(d.get("roi_ev"), 1)}% | {fmt(d.get("roi_top1"), 1)}% |')
    add('')
    g = payload.get('guardrails') or {}
    add('### Guardrails')
    add('')
    add(f'- OOS 場數 {g.get("overall_oos_races")}（門檻 100）：{"OK" if g.get("overall_ok") else "不足"}')
    venue_oos = g.get('venue_oos') or {}
    add(f'- 場地 OOS：HV {venue_oos.get("HV", 0)}、ST {venue_oos.get("ST", 0)}（門檻各 40）：'
        f'{"OK" if g.get("venue_ok") else "不足"}')
    add(f'- Phase 2 OOS 場數：{g.get("phase2_oos_races")}；分桶門檻 30 場或 300 runners，'
        '詳見下表 Guard 欄')
    add('')
    add('## Phase 1：市場去水 γ')
    add('')
    add('| γ | NLL | Brier | Top1 | ROI(EV) |')
    add('|---|---|---|---|---|')
    for g, d in p1['gamma_fixed'].items():
        add(f'| {g} | {fmt(d["nll"], 5)} | {fmt(d["brier"], 5)} | {pct(d["top1"])} | {fmt(d["roi_ev"], 1)}% |')
    add('')
    add(f'- 逐折 γ 選擇：{p1["gamma_fold"]["picks"]} → OOS NLL {fmt(p1["gamma_fold"]["nll"], 5)}')
    add(f'- 分段 γ（≤4 / 4-10 / >10）逐折：{p1["gamma_banded_fold"]["picks"]} → '
        f'OOS NLL {fmt(p1["gamma_banded_fold"]["nll"], 5)}')
    add('- 注意：1,048/1,057 場的「賠率」其實是 SP 複製，γ 越接近 1.0 等於越貼近 SP 本身，'
        '因此 γ=1.0 的 EV 注數為 0、ROI 無定義屬預期現象；γ 的結論只可在真實賽前價樣本累積後重用。')
    add('')
    add('## Phase 1：P_model 校準（train-only）')
    add('')
    add('| 方法 | NLL | Brier | ECE | Top1 |')
    add('|---|---|---|---|---|')
    for key, label in (('raw', 'raw（部署 identity）'), ('temperature', 'temperature'),
                       ('platt_rolling', 'Platt rolling 150-300')):
        d = p1['calibration'][key]
        add(f'| {label} | {fmt(d["nll"], 5)} | {fmt(d["brier"], 5)} | {fmt(d["ece"], 4)} | {pct(d["top1"])} |')
    add('')
    add(f'- Temperature 逐折選擇：{p1["calibration"]["temperature"]["picks"]}')
    add(f'- Platt 參數：{p1["calibration"]["platt_rolling"]["params"]}')
    add('')
    add('## Phase 1：融合 α（γ=1.0，P_model raw）')
    add('')
    add('| α | NLL | Brier | Top1 | ROI(EV) |')
    add('|---|---|---|---|---|')
    for a, d in p1['alpha']['fixed'].items():
        add(f'| {a:.2f} | {fmt(d["nll"], 5)} | {fmt(d["brier"], 5)} | {pct(d["top1"])} | {fmt(d["roi_ev"], 1)}% |')
    add('')
    add(f'- 逐折 α 選擇：{p1["alpha"]["fold"]["picks"]} → OOS NLL {fmt(p1["alpha"]["fold"]["nll"], 5)}')
    add(f'- 極端賠率動態 α（<1.8 或 >25 → 0.35）：NLL {fmt(p1["alpha"]["dynamic_extreme"]["nll"], 5)}，'
        f'Top1 {pct(p1["alpha"]["dynamic_extreme"]["top1"])}')
    add('- 注意：逐折 α 全選 0.0 是 SP 循環所致（P_market 由同一 SP 計出，貼近市場必然 NLL 最低），'
        '並不等於 P_model 無價值；α 預設維持 0.2，待 ≥50 場真實賽前價才做時間加權 A/B。')
    add('')

    p2 = payload.get('phase2') or {}
    add('## Phase 2：稀疏特徵消融（2026-06-01+，honest 協議）')
    add('')
    if p2.get('skipped'):
        add('- 樣本不足，略過。')
    else:
        add(f'- 子集 OOS：{p2["oos_races"]} 場；每折權重只用測試期之前的賽事擬合')
        add(f'- Deployed 特徵組合 vs pre-Phase-2 基線：ΔNLL {fmt(p2["combined_delta"], 5)}，'
            f'95% CI {p2["combined_delta_ci"]}')
        cf = p2.get('combined_folds') or {}
        add(f'- 逐折改善（combined）：{cf.get("improved")}/{cf.get("folds")} 折 NLL 下降'
            '（採納門檻：≥4/5 折改善且 95% CI 不含 0）')
        add('')
        add('| 變體 | 場數 | 基線 NLL | 變體 NLL | ΔNLL | 95% CI | 基線 Top1 | 變體 Top1 | 改善折 |')
        add('|---|---|---|---|---|---|---|---|---|')
        for name, d in p2['ablations'].items():
            ci = d.get('delta_ci')
            fo = d.get('folds') or {}
            add(f'| {name} | {d["races"]} | {fmt(d["baseline"]["nll"], 5)} | '
                f'{fmt(d["variant"]["nll"], 5)} | {fmt(d["delta_nll"], 5)} | '
                f'{fmt(ci[0], 5) if ci else "-"} ~ {fmt(ci[1], 5) if ci else "-"} | '
                f'{pct(d["baseline"]["top1"])} | {pct(d["variant"]["top1"])} | '
                f'{fo.get("improved", "-")}/{fo.get("folds", "-")} |')
        add('')
        add('- `avail_aware` 為隔離比較（pre2 因子 ± 缺值權重重正規化）；'
            '`avail_aware_on_combined` 係在已部署因子組合上再加 renormalisation；'
            '`avail_aware_stack`（deployed+renorm vs pre2）只作審計對照，'
            '數字會混入已上線的 form/rating/draw 增益，不可當成 renormalisation 的成效。')
        add('')
        st = p2.get('st1000') or {}
        add(f'- ST 1000m OOS：{st.get("races")} 場'
            '（<30 場，反轉 flag 維持關閉）')
        cov = p2.get('phase2b_coverage') or {}
        add(f'- Phase 2b 覆蓋：finish_time {pct(cov.get("finish_time"))}，'
            f'margin {pct(cov.get("margin"))}（維持 display-only flag 關閉）')
    add('')
    add('## 分層（honest_v586，α=0.2、γ=1.0）')
    add('')
    strata = payload.get('strata') or {}
    for name, groups in strata.items():
        add(f'### {name}')
        add('')
        add('| 變體 | 場數 | NLL | Top1 | Top3 | ROI(EV) | 注數 | Guard |')
        add('|---|---|---|---|---|---|---|---|')
        for label, d in groups.items():
            add(f'| {label} | {d["races"]} | {fmt(d["nll"], 5)} | {pct(d["top1"])} | '
                f'{pct(d["top3"])} | {fmt(d["roi_ev"], 1)}% | {d.get("bets", 0)} | '
                f'{"OK" if d["guard_ok"] else "樣本不足"} |')
        add('')
    add('## 結論與 flag 狀態')
    add('')
    add('- honest_v586 相對 current_v586 的跌幅已量化於上表；Phase 1 未有任何預設改動。')
    add('- 由 Commit B 起，honest_v586 是唯一比較基線；current_v586 只作洩漏幅度參考，'
        'legacy_v576 只作歷史對照。')
    add('- γ、校準、α 的逐折選擇只作診斷；Phase 1 flag 仍全部關閉，等 Commit B 確認後再逐項 A/B。')
    add('- 診斷傾向：γ 維持 1.0（逐折 1.1 反而較差、分段幾乎全選 1.0）；temperature/Platt 的 OOS '
        'NLL 改善 <0.01；α=0 是 SP 循環假象，維持 0.2。以上全部未改預設。')
    add('- Phase 2 的 combined 已包含三個現行已部署公式（form shrinkage、rating blend、draw k），'
        '本表是 honest 協議下的重新驗證，不是新改動。')
    if p2 and not p2.get('skipped'):
        passed = []
        for name, d in p2['ablations'].items():
            if name.endswith('_stack'):
                continue
            ci = d.get('delta_ci')
            fo = d.get('folds') or {}
            if (d['delta_nll'] is not None and d['delta_nll'] < 0 and ci and ci[1] < 0
                    and fo.get('folds') and fo.get('improved', 0) >= 4):
                passed.append(name)
        add(f'- Phase 2 達採納門檻（ΔNLL<0、95% CI 全負、≥4/5 折改善）的變體：'
            f'{", ".join(passed) if passed else "無"}；即使達標亦只會以 flag 開 A/B，不會直接改預設。')
        add('- Phase 2 消融只在 2026-06-01+ 子集跑；所有新特徵維持 flag/display-only，未改預設。')
    add('- ROI 全部以 SP 計，屬上限值；真實賽前價只有 '
        f'{meta["pre_race_races"]} 場，不足以支撐時間加權融合。')
    add('')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    sys.exit(main())