#!/usr/bin/env python3
"""
scripts/ai_review.py
Stage 3b: AI Post-Race Review Engine

Compares AI top-3 recommendations vs actual results, computes ROI/hit rate,
and generates a one-line AI review commentary.

Depends on: post_race_import.py must have run first (finish_position populated).

CLI:
  python scripts/ai_review.py --date 2026-10-04 --venue ST
  python scripts/ai_review.py --date 2026-10-04 --venue ST --race 1,2,3
  python scripts/ai_review.py --all
"""
import os
import sys
import json
import argparse
from typing import Dict, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase, has_column


def generate_review_commentary(
    race_no: int,
    top1_hit: bool,
    top3_hit_count: int,
    roi_percent: float,
    winner_odds: Optional[float],
    winner_p_model: Optional[float],
    total_bets: float,
    key_factors: List[Dict],
) -> str:
    """
    Generate a one-line AI post-race review commentary in Traditional Chinese.

    Priority order:
    1. Upset detection (longshot winner that AI missed)
    2. Top-1 hit + positive ROI
    3. Top-1 hit + negative ROI
    4. Top-3 partial hit
    5. Total miss
    """
    is_upset = winner_odds is not None and winner_odds >= 12.0
    ai_underestimated = (
        is_upset
        and winner_p_model is not None
        and winner_p_model < 0.10
    )

    if ai_underestimated:
        return (
            f"R{race_no} 爆冷：#{winner_odds:.0f}x 大冷門跑出，"
            f"AI 模型僅給 {winner_p_model * 100:.0f}% 勝率，"
            f"需檢討隱藏因素（騎師換馬/場地適性）"
        )

    if is_upset and not ai_underestimated:
        return (
            f"R{race_no} 冷門：#{winner_odds:.0f}x 馬胜出，"
            f"AI 有留意但賠率反映市場低估，屬可接受偏差"
        )

    if top1_hit and roi_percent > 0:
        return (
            f"R{race_no} AI 首選命中，"
            f"EV 策略回報 +{roi_percent:.0f}%，"
            f"模型判斷準確"
        )

    if top1_hit and roi_percent <= 0:
        return (
            f"R{race_no} AI 首選跑出，"
            f"但 EV 策略虧損 {roi_percent:.0f}%（其他冷門拖低），"
            f"需收緊入選門檻"
        )

    if top3_hit_count >= 2:
        return (
            f"R{race_no} AI 前三膽命中 {top3_hit_count}/3，"
            f"整體方向正確但首名未中，"
            f"位置 Q 策略可考慮"
        )

    if top3_hit_count == 1:
        return (
            f"R{race_no} AI 前三膽僅中 1/3，"
            f"命中率偏低，"
            f"建議檢視本場因素權重"
        )

    if total_bets > 0 and roi_percent < -50:
        return (
            f"R{race_no} AI 全數落空且重虧 {roi_percent:.0f}%，"
            f"本場存在模型未涵蓋的重大因素"
        )

    return (
        f"R{race_no} AI 預測落空，"
        f"前三膽全數未進前三，"
        f"累積數據用於權重修正"
    )


def review_single_race(supabase, race_id: str) -> Optional[Dict]:
    """
    Run AI review for a single race.
    Returns summary dict or None if race not ready.
    """
    race_info = supabase.table('races').select('race_date,venue,race_no').eq('race_id', race_id).single().execute()
    race_meta = race_info.data or {}
    race_no = race_meta.get('race_no', 0)

    runners_resp = supabase.table('race_runners').select('*').eq('race_id', race_id).execute()
    runners = runners_resp.data or []

    if not runners:
        print(f"  [SKIP] {race_id}: no runners")
        return None

    finished = [r for r in runners if r.get('finish_position') is not None]
    if not finished:
        print(f"  [SKIP] {race_id}: no finish positions (run post_race_import first)")
        return None

    finished.sort(key=lambda r: r['finish_position'])

    preds_resp = supabase.table('model_predictions').select('*').eq('race_id', race_id).execute()
    preds = preds_resp.data or []

    if not preds:
        print(f"  [WARN] {race_id}: no predictions")
        return None

    runner_map = {r['runner_id']: r for r in runners}
    pred_map = {p['runner_id']: p for p in preds}

    sorted_preds = sorted(preds, key=lambda p: p.get('final_prob') or p.get('raw_model_prob') or 0, reverse=True)

    top1_pred = sorted_preds[0]
    top1_runner = runner_map.get(top1_pred['runner_id'])
    top1_finish = top1_runner['finish_position'] if top1_runner else None
    top1_hit = top1_finish == 1 if top1_finish else False

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

    winner = finished[0]
    winner_odds = winner.get('win_odds')
    winner_pred = pred_map.get(winner['runner_id'])
    winner_p_model = None
    if winner_pred:
        winner_p_model = winner_pred.get('raw_model_prob') or winner_pred.get('final_prob')

    key_factors_list = _build_key_factors(winner, winner_odds, winner_p_model, top3_hit_count, finished)

    commentary = generate_review_commentary(
        race_no=race_no,
        top1_hit=top1_hit,
        top3_hit_count=top3_hit_count,
        roi_percent=roi_percent,
        winner_odds=winner_odds,
        winner_p_model=winner_p_model,
        total_bets=total_bets,
        key_factors=key_factors_list,
    )

    ai_perf = {
        'race_id': race_id,
        'race_date': race_meta.get('race_date'),
        'venue': race_meta.get('venue'),
        'race_no': race_no,
        'top1_pick_runner_id': top1_pred['runner_id'],
        'top1_pick_finish_pos': top1_finish,
        'top1_hit': top1_hit,
        'top3_picks': json.dumps(top3_info),
        'top3_hit_count': top3_hit_count,
        'total_bets': total_bets,
        'total_returns': round(total_returns, 2),
        'roi_percent': round(roi_percent, 2),
        'key_factors': json.dumps({
            'commentary': commentary,
            'factors': key_factors_list,
        }, ensure_ascii=False),
    }

    if has_column(supabase, 'ai_performance', 'pace_analysis'):
        pace = next((f['description'] for f in key_factors_list if f.get('type') == 'pace'), None)
        if pace:
            ai_perf['pace_analysis'] = pace
    if has_column(supabase, 'ai_performance', 'draw_bias'):
        draw = next((f['description'] for f in key_factors_list if f.get('type') == 'draw_bias'), None)
        if draw:
            ai_perf['draw_bias'] = draw
    if has_column(supabase, 'ai_performance', 'market_move'):
        market = next((f['description'] for f in key_factors_list if f.get('type') == 'upset'), None)
        if market:
            ai_perf['market_move'] = market

    try:
        retry_supabase(lambda: supabase.table('ai_performance').upsert(
            ai_perf, on_conflict='race_id'
        ).execute())
        print(f"  [OK] ai_performance written")
    except Exception as e:
        ai_perf_core = {k: v for k, v in ai_perf.items()
                        if k not in ('pace_analysis', 'draw_bias', 'market_move')}
        try:
            retry_supabase(lambda: supabase.table('ai_performance').upsert(
                ai_perf_core, on_conflict='race_id'
            ).execute())
            print(f"  [OK] ai_performance written (core only)")
        except Exception as e2:
            print(f"  [FAIL] ai_performance write failed: {e2}")
            return None

    return {
        'race_id': race_id,
        'race_no': race_no,
        'top1_hit': top1_hit,
        'top3_hit_count': top3_hit_count,
        'roi_percent': roi_percent,
        'winner_odds': winner_odds,
        'commentary': commentary,
    }


def _build_key_factors(winner: Dict, winner_odds: Optional[float],
                       winner_p_model: Optional[float],
                       top3_hit_count: int, finished: List[Dict]) -> List[Dict]:
    """Build structured key factors list for JSON storage."""
    factors = []

    winner_draw = winner.get('draw') or 0
    if winner_draw <= 3:
        factors.append({
            'type': 'draw_bias',
            'description': f'內檔 {winner_draw} 檔節省腳程',
            'impact': 'positive',
        })
    elif winner_draw >= 10:
        factors.append({
            'type': 'draw_bias',
            'description': f'外檔 {winner_draw} 檔克服不利條件',
            'impact': 'remarkable',
        })

    if winner_odds and winner_odds >= 12.0:
        factors.append({
            'type': 'upset',
            'description': f'大冷門 #{winner_odds:.0f}x，AI 勝率 {winner_p_model * 100:.0f}%' if winner_p_model else f'大冷門 #{winner_odds:.0f}x',
            'impact': 'upset',
        })
    elif winner_odds and winner_odds < 5 and winner_p_model and winner_p_model > 0.20:
        factors.append({
            'type': 'favorite_wins',
            'description': f'熱門馬 {winner_odds:.1f}x 奪冠，AI 勝率 {winner_p_model * 100:.0f}%',
            'impact': 'expected',
        })

    avg_weight = sum(r.get('actual_weight') or 126 for r in finished) / len(finished)
    if avg_weight < 122:
        factors.append({
            'type': 'pace',
            'description': f'平均負磅 {avg_weight:.1f}，快步速有利前領馬',
            'impact': 'pace_fast',
        })
    elif avg_weight > 128:
        factors.append({
            'type': 'pace',
            'description': f'平均負磅 {avg_weight:.1f}，慢步速有利後追馬',
            'impact': 'pace_slow',
        })

    if top3_hit_count >= 2:
        factors.append({
            'type': 'ai_accuracy',
            'description': f'AI 前三膽命中 {top3_hit_count}/3',
            'impact': 'ai_good',
        })
    elif top3_hit_count == 0:
        factors.append({
            'type': 'ai_miss',
            'description': 'AI 前三膽全數落空',
            'impact': 'ai_bad',
        })

    return factors


def main():
    parser = argparse.ArgumentParser(description='AI Post-Race Review Engine')
    parser.add_argument('--date', help='Race date (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--venue', choices=['ST', 'HV'], help='Venue code')
    parser.add_argument('--race', help='Comma-separated race numbers (e.g., 1,2,3)')
    parser.add_argument('--all', action='store_true', help='Review all finished races')
    args = parser.parse_args()

    today = datetime.now(HKT)
    date_str = args.date or today.strftime('%Y-%m-%d')

    supabase = get_supabase()

    if args.all:
        print("[AI Review] Analyzing all completed races...")
        runners_resp = supabase.table('race_runners').select('race_id,finish_position').not_.is_('finish_position', 'null').execute()
        race_ids = list(set(r['race_id'] for r in (runners_resp.data or [])))
        race_ids.sort()
    else:
        if not args.venue:
            weekday = today.weekday()
            if weekday in [2, 5]:
                venue = 'ST'
            elif weekday in [1, 3, 6]:
                venue = 'HV'
            else:
                print("[FAIL] Cannot auto-detect venue. Specify --venue ST or HV")
                sys.exit(1)
        else:
            venue = args.venue

        races_resp = supabase.table('races').select('race_id,race_no').eq('race_date', date_str).eq('venue', venue).execute()
        races = races_resp.data or []

        if args.race:
            race_nos = [int(x) for x in args.race.split(',')]
            races = [r for r in races if r['race_no'] in race_nos]

        race_ids = [r['race_id'] for r in races]

    if not race_ids:
        print("[FAIL] No races found to review")
        sys.exit(1)

    print(f"{'=' * 60}")
    print(f"AI Post-Race Review")
    print(f"Races to review: {len(race_ids)}")
    print(f"{'=' * 60}")

    results = []
    for race_id in race_ids:
        print(f"\n  Reviewing {race_id}...")
        summary = review_single_race(supabase, race_id)
        if summary:
            results.append(summary)
            print(f"  >> {summary['commentary']}")

    if results:
        print(f"\n{'=' * 60}")
        print(f"REVIEW SUMMARY")
        print(f"{'=' * 60}")
        total = len(results)
        top1_hits = sum(1 for r in results if r['top1_hit'])
        avg_top3 = sum(r['top3_hit_count'] for r in results) / total
        roi_values = [r['roi_percent'] for r in results if r['roi_percent'] != 0]
        avg_roi = sum(roi_values) / len(roi_values) if roi_values else 0

        print(f"  Races reviewed:   {total}")
        print(f"  Top-1 hit rate:   {top1_hits}/{total} ({top1_hits / total * 100:.1f}%)")
        print(f"  Avg Top-3 hits:   {avg_top3:.1f}/race")
        print(f"  Avg ROI (EV bet): {avg_roi:+.1f}%")
        print(f"{'=' * 60}")

        print(f"\n  Per-race commentaries:")
        for r in results:
            print(f"    {r['commentary']}")


if __name__ == '__main__':
    main()
