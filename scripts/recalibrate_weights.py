#!/usr/bin/env python3
"""
Refit the 9-factor weight tables from settled results (conditional logit).

The factors themselves are fixed 0-100 scores (same code the AI review uses);
only the weights are fitted. Fitting maximises the likelihood of the actual
winner under softmax(score / T), chronologically split so the published table
must beat the current one on races it has never seen.

Guardrails:
  - per-factor weight stays within ±0.06 of the current table
  - floors 0.02, cap 0.30, table renormalised to exactly 1.0
  - publish only when out-of-sample NLL improves
  - --auto skips until MIN_NEW_RACES have finished since the last fit

Usage:
  python scripts/recalibrate_weights.py --days 150 --dry-run
  python scripts/recalibrate_weights.py --days 150
  python scripts/recalibrate_weights.py --auto
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase, retry_supabase
from model_config import (ACTIVE_WEIGHTS_PATH, FACTOR_KEYS, SOFTMAX_TEMPERATURE,
                          raw_weights_for)
from ai_review import _fetch_horse_history, _predict_pace, compute_factor_scores

HKT = ZoneInfo('Asia/Hong_Kong')
STATUS_ID = 'model_weights_active'
MIN_NEW_RACES = 30
MIN_TRAIN = 40
MIN_TEST = 15
WEIGHT_FLOOR = 0.02
WEIGHT_CAP = 0.30
MAX_DRIFT = 0.06
RUNNER_COLS = ('runner_id,race_id,horse_id,horse_no,draw,actual_weight,jockey_win_rate,'
               'trainer_win_rate,rest_days,gear,form_history,recent_form_score,'
               'finish_position,win_odds')


def last_fit_time(supabase) -> Optional[str]:
    try:
        resp = retry_supabase(
            lambda: supabase.table('pipeline_status').select('last_run').eq('id', STATUS_ID).execute()
        )
        rows = resp.data or []
        return rows[0].get('last_run') if rows else None
    except Exception:
        return None


def new_finished_races(supabase, since_iso: Optional[str]) -> int:
    since = (since_iso or '2000-01-01T00:00:00+00:00')[:10]
    resp = retry_supabase(
        lambda: supabase.table('races')
        .select('race_id', count='exact')
        .eq('is_finished', True)
        .gte('race_date', since)
        .limit(1)
        .execute()
    )
    return resp.count or 0


def fetch_samples(supabase, since: str) -> List[Dict]:
    resp = retry_supabase(
        lambda: supabase.table('races')
        .select('race_id,race_date,venue,distance,class_level')
        .eq('is_finished', True)
        .gte('race_date', since)
        .in_('venue', ['ST', 'HV'])
        .order('race_date')
        .limit(400)
        .execute()
    )
    races = resp.data or []
    if not races:
        return []

    by_id = {r['race_id']: r for r in races}
    ids = list(by_id)
    runners: Dict[str, List[Dict]] = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(
                lambda c=chunk, o=offset: supabase.table('race_runners')
                .select(RUNNER_COLS).in_('race_id', c).order('runner_id')
                .range(o, o + 999).execute()
            ).data or []
            for g in got:
                runners.setdefault(g['race_id'], []).append(g)
            if len(got) < 1000:
                break
            offset += 1000

    horse_ids = list({r['horse_id'] for rows in runners.values() for r in rows if r.get('horse_id')})
    print(f'[Fit] fetching history for {len(horse_ids)} horses...')
    history = _fetch_horse_history(supabase, horse_ids)

    samples = []
    for rid, rows in runners.items():
        finishers = [r for r in rows if (r.get('finish_position') or 0) > 0]
        winner = next((r for r in finishers if r['finish_position'] == 1), None)
        if len(finishers) < 4 or not winner:
            continue
        race = by_id[rid]
        pace_label = _predict_pace(rows, history, str(race['race_date'])[:10])
        scores = []
        for r in rows:
            factors = compute_factor_scores(
                r, len(rows), race['venue'], race['distance'], race.get('class_level'),
                history, pace_label, str(race['race_date'])[:10],
            )
            scores.append([factors[k] for k in FACTOR_KEYS])
        samples.append({
            'race_id': rid,
            'race_date': str(race['race_date'])[:10],
            'venue': race['venue'],
            'scores': scores,
            'winner_idx': rows.index(winner),
        })
    samples.sort(key=lambda s: s['race_date'])
    return samples


def nll_and_grad(samples: List[Dict], w: List[float]) -> Tuple[float, List[float]]:
    total_nll = 0.0
    grad = [0.0] * len(w)
    temperature = SOFTMAX_TEMPERATURE
    for sample in samples:
        z = [sum(w[k] * sc[k] for k in range(len(w))) / temperature for sc in sample['scores']]
        peak = max(z)
        exps = [math.exp(v - peak) for v in z]
        norm = sum(exps)
        probs = [e / norm for e in exps]
        total_nll -= math.log(max(probs[sample['winner_idx']], 1e-12))
        for i, sc in enumerate(sample['scores']):
            coeff = (1.0 if i == sample['winner_idx'] else 0.0) - probs[i]
            for k in range(len(w)):
                grad[k] -= coeff * sc[k] / temperature
    n = max(len(samples), 1)
    return total_nll / n, [g / n for g in grad]


def project(weights: List[float], base: List[float]) -> List[float]:
    clipped = []
    for k, v in enumerate(weights):
        lo = max(WEIGHT_FLOOR, base[k] - MAX_DRIFT)
        hi = min(WEIGHT_CAP, base[k] + MAX_DRIFT)
        clipped.append(min(hi, max(lo, v)))
    total = sum(clipped)
    return [v / total for v in clipped]


def round_table(weights: List[float]) -> Dict[str, float]:
    """Round to 4dp but absorb the residual into the largest factor so the
    published table sums to exactly 1.0."""
    rounded = [round(v, 4) for v in weights]
    resid = round(1.0 - sum(rounded), 4)
    if resid:
        top = max(range(len(rounded)), key=lambda i: rounded[i])
        rounded[top] = round(rounded[top] + resid, 4)
    return {k: rounded[i] for i, k in enumerate(FACTOR_KEYS)}


def fit_venue(samples: List[Dict], base_table: Dict[str, float]) -> Optional[Dict]:
    split = int(len(samples) * 0.8)
    train, test = samples[:split], samples[split:]
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        return None

    base = [base_table[k] for k in FACTOR_KEYS]
    base_test_nll, _ = nll_and_grad(test, base)
    train_nll, _ = nll_and_grad(train, base)

    best_w = list(base)
    best_train = train_nll
    current = list(base)
    for step in range(300):
        _, grad = nll_and_grad(train, current)
        gmax = max(abs(g) for g in grad)
        if gmax < 1e-9:
            break
        lr = (0.012 / gmax) * (0.995 ** step)
        proposal = project([current[k] - lr * grad[k] for k in range(len(current))], base)
        loss, _ = nll_and_grad(train, proposal)
        if loss < best_train:
            best_w, best_train = proposal, loss
        current = proposal

    test_nll, _ = nll_and_grad(test, best_w)
    return {
        'weights': round_table(best_w),
        'train_races': len(train),
        'test_races': len(test),
        'train_nll': round(best_train, 5),
        'nll': round(test_nll, 5),
        'baseline_nll': round(base_test_nll, 5),
        'improved': test_nll < base_test_nll - 1e-4,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=150)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--auto', action='store_true', help='skip unless enough new races')
    args = parser.parse_args()

    supabase = get_supabase()
    if args.auto:
        since_fit = last_fit_time(supabase)
        fresh = new_finished_races(supabase, since_fit)
        if fresh < MIN_NEW_RACES:
            print(f'[Fit] {fresh} finished races since last fit (<{MIN_NEW_RACES}) — skipping')
            return 0
        print(f'[Fit] {fresh} finished races since {since_fit or "the beginning"} — refitting')

    since = (datetime.now(HKT) - timedelta(days=args.days)).strftime('%Y-%m-%d')
    samples = fetch_samples(supabase, since)
    print(f'[Fit] {len(samples)} usable races since {since}')

    results = {}
    improved_any = False
    for venue in ('HV', 'ST'):
        subset = [s for s in samples if s['venue'] == venue]
        base_table = raw_weights_for(venue)
        result = fit_venue(subset, base_table)
        if not result:
            print(f'  {venue}: {len(subset)} races — not enough to split, keeping current table')
            continue
        results[venue] = result
        flag = 'IMPROVED' if result['improved'] else 'no gain'
        print(f"  {venue}: train {result['train_races']} / test {result['test_races']} "
              f"| test NLL {result['nll']:.4f} vs baseline {result['baseline_nll']:.4f} ({flag})")
        if result['improved']:
            improved_any = True
            print('       ' + ' '.join(f"{k}={result['weights'][k]}" for k in FACTOR_KEYS))

    if args.dry_run:
        print('[Dry-run] nothing written')
        return 0
    if not improved_any:
        print('[Fit] no venue improved out-of-sample — keeping the current weights')
        return 0

    weights = {'HV': raw_weights_for('HV'), 'ST': raw_weights_for('ST')}
    for venue, result in results.items():
        if result['improved']:
            weights[venue] = result['weights']

    now_iso = datetime.now(HKT).isoformat()
    payload = {
        'fitted_at': now_iso,
        'sample_races': sum(r['train_races'] + r['test_races'] for r in results.values()),
        'nll': round(sum(r['nll'] for r in results.values()) / len(results), 5),
        'baseline_nll': round(sum(r['baseline_nll'] for r in results.values()) / len(results), 5),
        'venues': {v: {k: r[k] for k in ('train_races', 'test_races', 'nll', 'baseline_nll', 'improved')}
                   for v, r in results.items()},
        'weights': weights,
    }

    with open(ACTIVE_WEIGHTS_PATH, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f'[Fit] wrote {os.path.basename(ACTIVE_WEIGHTS_PATH)}')

    retry_supabase(lambda: supabase.table('pipeline_status').upsert({
        'id': STATUS_ID,
        'last_run': now_iso,
        'status_json': payload,
    }, on_conflict='id').execute())
    print('[Fit] published to pipeline_status.model_weights_active')
    return 0


if __name__ == '__main__':
    sys.exit(main())