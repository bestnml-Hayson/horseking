#!/usr/bin/env python3
"""
Recompute AI performance metrics for 2026-10-04 with updated odds.
"""
import os
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_supabase, retry_supabase


def recompute_race(supabase, race_id: str) -> dict:
    """Recompute AI performance for a single race."""
    # Get race metadata
    race_info = supabase.table('races').select('race_date,venue,race_no').eq('race_id', race_id).single().execute()
    race_meta = race_info.data or {}
    race_no = race_meta.get('race_no', 0)

    # Get runners
    runners_resp = supabase.table('race_runners').select('*').eq('race_id', race_id).execute()
    runners = runners_resp.data or []

    if not runners:
        print(f"  [SKIP] {race_id}: no runners")
        return None

    finished = [r for r in runners if r.get('finish_position') is not None]
    if not finished:
        print(f"  [SKIP] {race_id}: no finish positions")
        return None

    finished.sort(key=lambda r: r['finish_position'])

    # Get predictions
    preds_resp = supabase.table('model_predictions').select('*').eq('race_id', race_id).execute()
    preds = preds_resp.data or []

    if not preds:
        print(f"  [WARN] {race_id}: no predictions")
        return None

    runner_map = {r['runner_id']: r for r in runners}
    pred_map = {p['runner_id']: p for p in preds}

    # Sort predictions by final_prob
    sorted_preds = sorted(preds, key=lambda p: p.get('final_prob') or p.get('raw_model_prob') or 0, reverse=True)

    # Top 1 pick
    top1_pred = sorted_preds[0]
    top1_runner = runner_map.get(top1_pred['runner_id'])
    top1_finish = top1_runner['finish_position'] if top1_runner else None
    top1_hit = top1_finish == 1 if top1_finish else False

    # Top 3 picks
    top3_preds = sorted_preds[:3]
    top3_info = []
    top3_hit_count = 0
    for p in top3_preds:
        r = runner_map.get(p['runner_id'])
        if r:
            finish_pos = r.get('finish_position')
            hit = finish_pos is not None and finish_pos <= 3
            if hit:
                top3_hit_count += 1
            top3_info.append({
                'runner_id': p['runner_id'],
                'horse_no': r.get('horse_no'),
                'finish_pos': finish_pos,
                'predicted_prob': p.get('final_prob') or p.get('raw_model_prob'),
                'hit': hit,
            })

    # ROI calculation with REAL odds
    total_bets = 0
    total_returns = 0
    for p in sorted_preds:
        ev = p.get('expected_value') or 0
        if ev > 0.15:
            r = runner_map.get(p['runner_id'])
            if r and r.get('win_odds') and r.get('finish_position'):
                bet_amount = 100
                total_bets += bet_amount
                if r['finish_position'] == 1:
                    total_returns += bet_amount * r['win_odds']

    roi_percent = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0

    # Update ai_performance table
    ai_perf_update = {
        'top1_hit': top1_hit,
        'top3_hit_count': top3_hit_count,
        'total_bets': total_bets,
        'total_returns': total_returns,
        'roi_percent': roi_percent,
        'top1_pick_runner_id': top1_pred['runner_id'],
        'top1_pick_finish_pos': top1_finish,
        'top3_picks': json.dumps(top3_info, ensure_ascii=False),
    }

    retry_supabase(lambda: supabase.table('ai_performance').update(ai_perf_update).eq('race_id', race_id).execute())

    print(f"  [OK] R{race_no}: bets={total_bets}, returns={total_returns}, roi={roi_percent:.1f}%, top1_hit={top1_hit}, top3={top3_hit_count}/3")

    return {
        'race_id': race_id,
        'total_bets': total_bets,
        'total_returns': total_returns,
        'roi_percent': roi_percent,
        'top1_hit': top1_hit,
        'top3_hit_count': top3_hit_count,
    }


def main():
    date_str = '2026-10-04'
    venue = 'ST'

    supabase = get_supabase()
    if not supabase:
        sys.exit(1)

    # Fetch races for this date/venue
    query = supabase.table('races').select('race_id,race_no').eq('race_date', date_str).eq('venue', venue)
    resp = query.execute()
    races = resp.data or []

    if not races:
        print(f"[FAIL] No races found for {date_str} {venue}")
        return

    print(f"=" * 60)
    print(f"Recompute AI Performance - {date_str} {venue}")
    print(f"Races: {len(races)}")
    print(f"=" * 60)

    total_bets = 0
    total_returns = 0
    top1_hits = 0
    top3_hits = 0

    for race in races:
        race_id = race['race_id']
        race_no = race['race_no']

        print(f"\n  Processing R{race_no} ({race_id})...")

        result = recompute_race(supabase, race_id)

        if result:
            total_bets += result['total_bets']
            total_returns += result['total_returns']
            if result['top1_hit']:
                top1_hits += 1
            top3_hits += result['top3_hit_count']

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Total bets: ${total_bets}")
    print(f"  Total returns: ${total_returns}")
    print(f"  Net profit: ${total_returns - total_bets}")
    print(f"  Win rate: {top1_hits}/{len(races)} = {top1_hits/len(races)*100:.1f}%")
    print(f"  Top3 hits: {top3_hits}/{len(races)*3} = {top3_hits/(len(races)*3)*100:.1f}%")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
