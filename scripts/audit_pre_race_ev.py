#!/usr/bin/env python3
"""
Score the live model at the price it actually offered, not the post-race SP.

Every earlier ROI audit used race_runners.win_odds after the archive write-back,
which is the official SP — a price nobody could still take. Since v5.77 the
archive keeps the pre-race price in race_runners and the SP in race_results, so
the two can finally be compared on the same selections.

Usage:
  python scripts/audit_pre_race_ev.py --since 2026-11-20
  python scripts/audit_pre_race_ev.py --since 2026-11-01 --min-races 30
"""
import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.path.insert(0, os.path.dirname(__file__))

from common import get_supabase, retry_supabase
from ai_review import compute_client_predictions_py, _fetch_horse_history

HKT = ZoneInfo('Asia/Hong_Kong')
EV_THRESHOLD = 0.15
STAKE = 100


def fetch_races(supabase, since: str) -> List[Dict]:
    resp = retry_supabase(
        lambda: supabase.table('races')
        .select('race_id,race_date,venue,race_no,distance,class_level')
        .eq('is_finished', True)
        .gte('race_date', since)
        .in_('venue', ['ST', 'HV'])
        .order('race_date')
        .limit(400)
        .execute()
    )
    return resp.data or []


def fetch_runners_by_race(supabase, ids: List[str]) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(
                lambda c=chunk, o=offset: supabase.table('race_runners')
                .select('*').in_('race_id', c).order('runner_id').range(o, o + 999).execute()
            ).data or []
            for g in got:
                out.setdefault(g['race_id'], []).append(g)
            if len(got) < 1000:
                break
            offset += 1000
    return out


def fetch_sp_by_race(supabase, ids: List[str]) -> Dict[str, Dict[int, float]]:
    out: Dict[str, Dict[int, float]] = {}
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        offset = 0
        while True:
            got = retry_supabase(
                lambda c=chunk, o=offset: supabase.table('race_results')
                .select('race_id,horse_no,win_odds').in_('race_id', c)
                .order('id').range(o, o + 999).execute()
            ).data or []
            for g in got:
                if g.get('win_odds') and g['win_odds'] > 1:
                    out.setdefault(g['race_id'], {})[g['horse_no']] = float(g['win_odds'])
            if len(got) < 1000:
                break
            offset += 1000
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', default='2026-11-20')
    parser.add_argument('--min-races', type=int, default=30)
    args = parser.parse_args()

    supabase = get_supabase()
    races = fetch_races(supabase, args.since)
    if not races:
        print(f'[Audit] no finished races since {args.since}')
        return 0

    ids = [r['race_id'] for r in races]
    runners = fetch_runners_by_race(supabase, ids)
    sp_map = fetch_sp_by_race(supabase, ids)

    horse_ids = list({r['horse_id'] for rows in runners.values() for r in rows if r.get('horse_id')})
    history = _fetch_horse_history(supabase, horse_ids)

    usable = 0
    sp_copies = 0
    bets = 0
    hits_pre = 0
    stake_total = 0
    returns_pre = 0.0
    returns_sp = 0.0
    top1_races = 0
    top1_hits = 0
    price_gaps = []

    for race in races:
        rid = race['race_id']
        rows = runners.get(rid) or []
        sp = sp_map.get(rid) or {}
        if len(rows) < 4:
            continue
        # Both prices must exist for every priced runner; partial coverage would
        # compare the model at two different fields.
        priced = [r for r in rows if r.get('win_odds') and r['win_odds'] > 1]
        if len(priced) < max(4, int(len(rows) * 0.8)):
            continue
        if not any(r.get('finish_position') == 1 for r in rows):
            continue
        # A race where every runner's stored price equals its SP was archived
        # after the off with no live odds captured — the "pre-race" price is
        # just the SP copy, which nobody could have bet.
        genuine = [r for r in priced if r['horse_no'] in sp
                   and abs(float(sp[r['horse_no']]) - float(r['win_odds'])) > 1e-9]
        if not genuine:
            sp_copies += 1
            continue
        usable += 1

        predicted = compute_client_predictions_py(
            rows, race['venue'], race['venue'], race['distance'], race.get('class_level'),
            history, str(race['race_date'])[:10],
        )
        if not predicted:
            continue
        by_runner = {r['runner_id']: r for r in rows}

        top = by_runner.get(predicted[0][0])
        if top:
            top1_races += 1
            if top.get('finish_position') == 1:
                top1_hits += 1

        for runner_id, _p_model, p_final in predicted:
            runner = by_runner.get(runner_id)
            if not runner or not runner.get('win_odds') or runner['win_odds'] <= 1:
                continue
            ev = p_final * runner['win_odds'] - 1
            if ev <= EV_THRESHOLD:
                continue
            horse_no = runner['horse_no']
            if horse_no not in sp:
                continue
            bets += 1
            stake_total += STAKE
            price_gaps.append((runner['win_odds'], sp[horse_no]))
            if runner.get('finish_position') == 1:
                hits_pre += 1
                returns_pre += STAKE * runner['win_odds']
                returns_sp += STAKE * sp[horse_no]

    print(f'\n[Pre-race EV audit] since {args.since}')
    print(f'  usable races            : {usable} (min {args.min_races} to call it a sample)')
    if sp_copies:
        print(f'  excluded (SP copy)      : {sp_copies} race(s) archived with no live pre-race odds')
    print(f'  top-1 hit rate          : {top1_hits}/{top1_races}'
          f' ({top1_hits / top1_races * 100:.1f}%)' if top1_races else '  top-1 hit rate          : n/a')
    if bets:
        roi_pre = (returns_pre - stake_total) / stake_total * 100
        roi_sp = (returns_sp - stake_total) / stake_total * 100
        print(f'  EV>{EV_THRESHOLD} bets          : {bets}, hits {hits_pre}')
        print(f'  ROI at pre-race price   : {roi_pre:+.1f}%')
        print(f'  ROI at official SP      : {roi_sp:+.1f}%')
        print(f'  SP worth over pre-price : {roi_sp - roi_pre:+.1f} pts')
    else:
        print(f'  EV>{EV_THRESHOLD} bets          : 0')
    if price_gaps:
        gaps = [abs((sp - pre) / pre) for pre, sp in price_gaps]
        mean_gap = sum(gaps) / len(gaps) * 100
        print(f'  |SP - pre-race| / price : {mean_gap:.1f}% mean over {len(gaps)} bets')

    if usable < args.min_races:
        print(f'  [WARN] only {usable} races — sample below {args.min_races}, treat as indicative only')
    return 0


if __name__ == '__main__':
    sys.exit(main())