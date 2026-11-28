#!/usr/bin/env python3
"""Shadow-mode predictions for default-off Phase 1/2 experiments.

The live pipeline never reads this record: model_predictions, race_runners and the
client-side P_final stay untouched. Each tick appends live vs shadow columns to
pipeline_status.shadow_predictions so the experiments can be scored on races that
carry genuine pre-race odds or missing prices.

Shadow columns:
  availability_gate - valid win-odds coverage below min_coverage forces the market
                      weight to sparse_market_weight (0 -> P_final = P_model)
  draw_v2           - draw v2 is already live; this column is an identity check
  avail_aware       - weights of factors with missing inputs dropped and renormalised
                      (mirrors the backtested variant, which had no coverage gate;
                      min_coverage is carried for future gating only)

CLI:
  python scripts/shadow_predictions.py --date 2026-12-02 --venue ST
  python scripts/shadow_predictions.py --date 2026-12-02 --venue ST --race 1,2,3
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase
from model_config import (
    EXPERIMENTS, FACTOR_KEYS, PROFILE_NAME, calibrate_p_model, fuse_race,
    market_probabilities, weights_for,
)
import ai_review as A

SHADOW_ID = 'shadow_predictions'
SHADOW_KEEP_DAYS = 7


def odds_coverage(odds):
    """(covered, total, ratio) for prices that can enter market_probabilities."""
    total = len(odds)
    covered = sum(1 for o in odds if o is not None and o > 1.0)
    return covered, total, (covered / total if total else 0.0)


def _masked_markets(odds):
    covered = sum(1 for o in odds if o is not None and o > 1.0)
    if not covered:
        return None
    markets = market_probabilities(odds)
    return [markets[i] if odds[i] is not None and odds[i] > 1.0 else None
            for i in range(len(odds))]


def availability_gate(experiment, p_models, odds):
    """Sparse-odds races fall back to model-only (or sparse_market_weight)."""
    cfg = experiment or {}
    min_cov = float(cfg.get('min_coverage', 0.8))
    sparse_wm = float(cfg.get('sparse_market_weight', 0.0))
    covered, total, coverage = odds_coverage(odds)
    info = {'coverage': round(coverage, 4), 'covered': covered, 'total': total,
            'min_coverage': min_cov, 'enabled': bool(cfg.get('enabled'))}
    if total and coverage < min_cov:
        calibrated = calibrate_p_model(p_models)
        markets = _masked_markets(odds) if sparse_wm > 0 else None
        finals = []
        for i, p in enumerate(calibrated):
            market = markets[i] if markets else None
            if market is None:
                finals.append(p)
            else:
                finals.append((1 - sparse_wm) * p + sparse_wm * market)
        info.update({'gate': 'sparse', 'market_weight': sparse_wm})
        return finals, info
    info.update({'gate': 'covered', 'market_weight': None})
    return fuse_race(p_models, _masked_markets(odds), odds), info


def avail_aware(experiment, factor_scores, availability, weights, p_models, odds):
    """Drop the weights of factors whose inputs are missing, then renormalise."""
    cfg = experiment or {}
    scores, meta = [], []
    for i, factors in enumerate(factor_scores):
        used = [k for k in FACTOR_KEYS if availability[i].get(k, True)]
        used_weight = sum(weights[k] for k in used)
        wsum = used_weight or 1.0
        scores.append(sum(factors[k] * weights[k] for k in used) / wsum)
        meta.append({
            'used_weight': round(used_weight, 4),
            'missing': [k for k in FACTOR_KEYS if not availability[i].get(k, True)],
        })
    shadow_models = A._softmax(scores)
    finals = fuse_race(shadow_models, _masked_markets(odds), odds)
    info = {'min_coverage': float(cfg.get('min_coverage', 0.8)),
            'gate': 'always', 'enabled': bool(cfg.get('enabled'))}
    return finals, info, meta


def race_shadow(runners, venue, distance, class_level, race_date, history,
                race_no=None, experiments=None):
    """Compute live and shadow columns for one race (None when no runners)."""
    n = len(runners)
    if not n:
        return None
    experiments = experiments if experiments is not None else EXPERIMENTS

    pace_label = A._predict_pace(runners, history, race_date)
    field_ratings = [r.get('official_rating') for r in runners]
    factor_scores = [
        A.compute_factor_scores(r, n, venue, distance, class_level, history,
                                pace_label, race_date, field_ratings)
        for r in runners
    ]
    availability = [
        A.factor_availability(r, n, venue, distance, class_level, history, race_date)
        for r in runners
    ]
    weights = weights_for(venue)
    base_scores = [sum(f[k] * weights[k] for k in FACTOR_KEYS) for f in factor_scores]
    p_models = A._softmax(base_scores)
    odds = [r.get('win_odds') for r in runners]

    live = fuse_race(p_models, _masked_markets(odds), odds)
    gate_finals, gate_info = availability_gate(
        experiments.get('availability_gate'), p_models, odds)
    aware_finals, aware_info, aware_meta = avail_aware(
        experiments.get('avail_aware'), factor_scores, availability, weights, p_models, odds)

    live_map, gate_map, aware_map = {}, {}, {}
    for i, runner in enumerate(runners):
        rid = runner['runner_id']
        live_map[rid] = {'p_model': round(p_models[i], 5), 'p_final': round(live[i], 5)}
        gate_map[rid] = {'p_final': round(gate_finals[i], 5)}
        aware_map[rid] = {'p_final': round(aware_finals[i], 5), **aware_meta[i]}

    covered, total, coverage = odds_coverage(odds)
    return {
        'race_no': race_no,
        'generated_at': datetime.now(HKT).isoformat(),
        'profile': PROFILE_NAME,
        'meta': {'runners': n, 'covered': covered, 'total': total,
                 'odds_coverage': round(coverage, 4)},
        'flags': {
            'availability_gate': bool((experiments.get('availability_gate') or {}).get('enabled')),
            'draw_v2': bool((experiments.get('draw_v2') or {}).get('enabled')),
            'avail_aware': bool((experiments.get('avail_aware') or {}).get('enabled')),
        },
        'live': live_map,
        'shadow': {
            'availability_gate': {'meta': gate_info, 'runners': gate_map},
            'draw_v2': {'meta': {'status': 'already_live'},
                        'runners': {rid: {'p_final': row['p_final']}
                                    for rid, row in live_map.items()}},
            'avail_aware': {'meta': aware_info, 'runners': aware_map},
        },
    }


def _load_state(supabase):
    try:
        resp = retry_supabase(
            lambda: supabase.table('pipeline_status').select('status_json')
            .eq('id', SHADOW_ID).execute()
        )
        rows = resp.data or []
        return (rows[0].get('status_json') or {}) if rows else {}
    except Exception as e:
        print(f"    [WARN] shadow state unreadable: {e}")
        return {}


def record_shadow_predictions(supabase, date_str, venue, race_nos=None):
    """Compute and upsert shadow columns for one meeting; returns race count."""
    query = supabase.table('races').select(
        'race_id,race_no,race_date,venue,distance,class_level,is_finished'
    ).eq('race_date', date_str).eq('venue', venue).order('race_no')
    races = retry_supabase(lambda: query.execute()).data or []
    if race_nos:
        wanted = set(race_nos)
        races = [r for r in races if r['race_no'] in wanted]
    races = [r for r in races if not r.get('is_finished')]
    if not races:
        print('    [Shadow] no open races to record')
        return 0

    race_ids = [r['race_id'] for r in races]
    runners_resp = retry_supabase(
        lambda: supabase.table('race_runners').select('*').in_('race_id', race_ids).execute())
    runners = runners_resp.data or []
    by_race = {}
    for row in runners:
        by_race.setdefault(row['race_id'], []).append(row)
    horse_ids = [r.get('horse_id') for r in runners if r.get('horse_id')]
    history = A._fetch_horse_history(supabase, horse_ids)

    now = datetime.now(HKT)
    state = _load_state(supabase)
    bag = state.get('races') or {}
    recorded = 0
    for race in races:
        rows = by_race.get(race['race_id']) or []
        record = race_shadow(
            rows, race.get('venue') or venue, race.get('distance'),
            race.get('class_level'), str(race.get('race_date') or date_str)[:10],
            history, race.get('race_no'), EXPERIMENTS,
        )
        if record is None:
            continue
        record['race_date'] = date_str
        bag[race['race_id']] = record
        recorded += 1

    cutoff = (now - timedelta(days=SHADOW_KEEP_DAYS)).strftime('%Y-%m-%d')
    bag = {rid: v for rid, v in bag.items()
           if str(v.get('race_date', ''))[:10] >= cutoff}
    retry_supabase(lambda: supabase.table('pipeline_status').upsert({
        'id': SHADOW_ID,
        'last_run': now.isoformat(),
        'status_json': {'races': bag, 'updated_at': now.isoformat()},
    }, on_conflict='id').execute())
    print(f"    [Shadow] recorded {recorded} races ({len(bag)} kept, {SHADOW_KEEP_DAYS}d)")
    return recorded


def main():
    parser = argparse.ArgumentParser(description='Shadow predictions (default-off flags)')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Defaults to today HKT.')
    parser.add_argument('--venue', choices=['ST', 'HV'], required=True)
    parser.add_argument('--race', help='Comma-separated race numbers (e.g. 1,2,3)')
    args = parser.parse_args()

    date_str = args.date or datetime.now(HKT).strftime('%Y-%m-%d')
    race_nos = [int(x) for x in args.race.split(',')] if args.race else None
    supabase = get_supabase()
    if not supabase:
        return 1
    record_shadow_predictions(supabase, date_str, args.venue, race_nos)
    return 0


if __name__ == '__main__':
    sys.exit(main())