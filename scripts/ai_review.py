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
import math
import re
import argparse
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase, retry_supabase, has_column


# =====================================================================
# Client-side prediction formula (matches lib/race-utils.ts exactly)
# =====================================================================
MODEL_WEIGHT = 0.5
MARKET_WEIGHT = 0.5
SOFTMAX_TEMPERATURE = 15

WEIGHTS_ST = {
    'form': 0.16, 'draw': 0.08, 'jockeyTrainer': 0.14, 'weight': 0.08,
    'courseDistance': 0.18, 'restDays': 0.10, 'gear': 0.06, 'pace': 0.10, 'classMov': 0.10,
}
WEIGHTS_HV = {
    'form': 0.18, 'draw': 0.14, 'jockeyTrainer': 0.12, 'weight': 0.08,
    'courseDistance': 0.16, 'restDays': 0.10, 'gear': 0.06, 'pace': 0.08, 'classMov': 0.08,
}


def _parse_form_history(form: Optional[str]) -> List[int]:
    if not form:
        return []
    cleaned = re.sub(r'[{}"\':]', ' ', form)
    numbers = re.findall(r'\d+', cleaned)
    return [int(n) for n in numbers if 0 < int(n) <= 20][:6]


def _softmax(scores: List[float], temperature: float = SOFTMAX_TEMPERATURE) -> List[float]:
    if not scores:
        return []
    max_s = max(scores)
    exps = [math.exp((s - max_s) / temperature) for s in scores]
    total = sum(exps)
    if total == 0:
        return [1.0 / len(scores)] * len(scores)
    return [e / total for e in exps]


def _predict_pace(runners: List[Dict]) -> str:
    if not runners:
        return '中等步速'
    avg_weight = sum(r.get('actual_weight') or 126 for r in runners) / len(runners)
    if avg_weight < 122:
        return '快步速'
    elif avg_weight > 128:
        return '慢步速'
    return '中等步速'


def _compute_course_distance_score(row: Dict, race_venue: Optional[str],
                                   race_distance: Optional[int],
                                   horse_history: Dict[str, List[Dict]]) -> float:
    if not race_venue or not race_distance or not horse_history:
        return 50
    history = horse_history.get(row.get('horse_id', ''), [])
    if not history:
        return 50
    same_venue_dist = [h for h in history if h.get('venue') == race_venue and h.get('distance') == race_distance]
    if not same_venue_dist:
        same_venue = [h for h in history if h.get('venue') == race_venue]
        if not same_venue:
            return 45
        recent = same_venue[:5]
        avg_pos = sum(h['finish_position'] for h in recent) / len(recent)
        return max(0, min(100, (1 - (avg_pos - 1) / 13) * 100))
    recent = same_venue_dist[:5]
    wins = sum(1 for h in recent if h['finish_position'] == 1)
    top3 = sum(1 for h in recent if h['finish_position'] <= 3)
    avg_pos = sum(h['finish_position'] for h in recent) / len(recent)
    score = 50 + wins * 15 + (top3 - wins) * 6 + max(0, (5 - avg_pos) * 5)
    return max(0, min(100, score))


def _compute_rest_days_score(row: Dict) -> float:
    rest = row.get('rest_days')
    if rest is None:
        return 50
    if 21 <= rest <= 42:
        return 85 + min(15, (rest - 21) * 0.5)
    if 14 <= rest < 21:
        return 65 + (rest - 14) * 3
    if 42 < rest <= 60:
        return 75 - (rest - 42) * 0.5
    if 60 < rest <= 90:
        return 65 - (rest - 60) * 0.3
    if rest < 14:
        return 30 + rest * 2
    return 40


def _compute_gear_score(row: Dict) -> float:
    gear = row.get('gear')
    if not gear:
        return 50
    parts = [g.strip() for g in gear.split('/') if g.strip()]
    new_gear = [g for g in parts if g.endswith('1')]
    if not new_gear:
        return 50
    score = 50
    for g in new_gear:
        base = g[:-1]
        if base == 'B':
            score += 14
        elif base in ('PC', 'H'):
            score += 10
        elif base in ('TT', 'XB'):
            score += 6
        else:
            score += 8
    return max(0, min(100, score))


def _compute_pace_score(row: Dict, pace_label: str, total_runners: int) -> float:
    draw = row.get('draw')
    form = _parse_form_history(row.get('form_history'))
    form_avg = sum(form) / len(form) if form else 8
    score = 50
    if pace_label == '快步速':
        if draw is not None and draw >= 10:
            score += 18
        elif draw is not None and draw >= 7:
            score += 10
        if form_avg > 6:
            score += 12
        if draw is not None and draw <= 4:
            score -= 10
    elif pace_label == '慢步速':
        if draw is not None and draw <= 4:
            score += 18
        elif draw is not None and draw <= 6:
            score += 10
        if form_avg <= 4:
            score += 12
        if draw is not None and draw >= 10:
            score -= 10
    return max(0, min(100, score))


def _compute_class_movement_score(row: Dict, race_class: Optional[str],
                                  horse_history: Dict[str, List[Dict]]) -> float:
    if not race_class or not horse_history:
        return 50
    history = horse_history.get(row.get('horse_id', ''), [])
    if not history:
        return 50
    recent_class = history[0].get('class_level', '')
    if not recent_class:
        return 50

    def class_order(c: str) -> int:
        m = re.search(r'(\d+)', c)
        return int(m.group(1)) if m else 5

    current = class_order(race_class)
    prev = class_order(recent_class)
    diff = prev - current
    if diff > 0:
        return min(100, 65 + diff * 10)
    if diff < 0:
        return max(0, 50 + diff * 8)
    return 55


def _compute_total_score(row: Dict, total_runners: int, venue: Optional[str],
                         race_venue: Optional[str], race_distance: Optional[int],
                         race_class: Optional[str],
                         horse_history: Dict[str, List[Dict]],
                         pace_label: str) -> float:
    w = WEIGHTS_HV if venue == 'HV' else WEIGHTS_ST

    form = _parse_form_history(row.get('form_history'))
    form_avg = sum(form) / len(form) if form else 10
    form_score = max(0, min(100, (1 - (form_avg - 1) / 13) * 100))

    draw = row.get('draw')
    draw_max = max(14, total_runners)
    draw_score = max(0, min(100, (1 - (draw - 1) / draw_max) * 100)) if draw is not None else 50

    jockey_wr = row.get('jockey_win_rate') or 0.1
    trainer_wr = row.get('trainer_win_rate') or 0.1
    jockey_score = max(0, min(100, jockey_wr * 500))
    trainer_score = max(0, min(100, trainer_wr * 500))
    jt_score = jockey_score * 0.6 + trainer_score * 0.4

    weight = row.get('actual_weight')
    weight_score = 60
    if weight is not None:
        if weight <= 118:
            weight_score += 20
        elif weight <= 124:
            weight_score += 10
        elif weight >= 132:
            weight_score -= 15
        elif weight >= 128:
            weight_score -= 5
    weight_score = max(0, min(100, weight_score))

    cd_score = _compute_course_distance_score(row, race_venue, race_distance, horse_history)
    rest_score = _compute_rest_days_score(row)
    gear_score = _compute_gear_score(row)
    pace_score = _compute_pace_score(row, pace_label, total_runners)
    class_score = _compute_class_movement_score(row, race_class, horse_history)

    return (form_score * w['form'] + draw_score * w['draw'] + jt_score * w['jockeyTrainer'] +
            weight_score * w['weight'] + cd_score * w['courseDistance'] + rest_score * w['restDays'] +
            gear_score * w['gear'] + pace_score * w['pace'] + class_score * w['classMov'])


def compute_client_predictions_py(runners: List[Dict], venue: Optional[str],
                                  race_venue: Optional[str], race_distance: Optional[int],
                                  race_class: Optional[str],
                                  horse_history: Dict[str, List[Dict]]) -> List[Tuple[str, float, float]]:
    """
    Compute predictions using the same 9-factor formula as the frontend.
    Returns list of (runner_id, p_model, p_final) tuples sorted by p_final desc.
    """
    if not runners:
        return []

    pace_label = _predict_pace(runners)
    total = len(runners)

    scores = [
        _compute_total_score(r, total, venue, race_venue, race_distance, race_class, horse_history, pace_label)
        for r in runners
    ]
    p_models = _softmax(scores)

    odds_list = [r.get('win_odds') for r in runners]
    has_valid_odds = any(o is not None and o > 1 for o in odds_list)

    if has_valid_odds:
        p_raw = [1.0 / o if o is not None and o > 1 else 0 for o in odds_list]
        sum_p_raw = sum(p_raw)
    else:
        p_raw = None
        sum_p_raw = 0

    results = []
    for i, runner in enumerate(runners):
        p_model = p_models[i]
        if has_valid_odds and sum_p_raw > 0:
            p_market = p_raw[i] / sum_p_raw
        else:
            p_market = None

        if p_market is not None:
            p_final = MODEL_WEIGHT * p_model + MARKET_WEIGHT * p_market
        else:
            p_final = p_model

        results.append((runner['runner_id'], p_model, p_final))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def _fetch_horse_history(supabase, horse_ids: List[str]) -> Dict[str, List[Dict]]:
    """Fetch horse race history for course/distance and class movement scoring."""
    history_map: Dict[str, List[Dict]] = {}
    if not horse_ids:
        return history_map

    batch_size = 50
    for i in range(0, len(horse_ids), batch_size):
        batch = horse_ids[i:i + batch_size]
        id_filter = ','.join(f'"{h}"' for h in batch)
        try:
            resp = supabase.table('race_runners').select(
                'horse_id,finish_position,races!inner(race_date,venue,distance,class_level)'
            ).in_('horse_id', batch).not_is_('finish_position', 'null').limit(2000).execute()
            for row in (resp.data or []):
                fp = row.get('finish_position')
                if fp is None or fp <= 0:
                    continue
                race = row.get('races')
                if isinstance(race, list):
                    race = race[0] if race else None
                if not race or not race.get('venue') or not race.get('distance'):
                    continue
                entry = {
                    'venue': race['venue'],
                    'distance': race['distance'],
                    'finish_position': fp,
                    'race_date': race.get('race_date', ''),
                    'class_level': race.get('class_level', ''),
                }
                hid = row['horse_id']
                history_map.setdefault(hid, []).append(entry)
        except Exception:
            pass

    for records in history_map.values():
        records.sort(key=lambda r: r['race_date'], reverse=True)

    return history_map


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
    race_info = supabase.table('races').select('race_date,venue,race_no,distance,class_level').eq('race_id', race_id).single().execute()
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

    # Compute predictions using same client formula as frontend
    race_venue = race_meta.get('venue')
    race_distance = race_meta.get('distance')
    race_class = race_meta.get('class_level')

    horse_ids = [r.get('horse_id') for r in runners if r.get('horse_id')]
    horse_history = _fetch_horse_history(supabase, horse_ids)
    client_preds = compute_client_predictions_py(
        runners, race_venue, race_venue, race_distance, race_class, horse_history
    )

    if not client_preds:
        print(f"  [WARN] {race_id}: no predictions computed")
        return None

    runner_map = {r['runner_id']: r for r in runners}
    pred_map = {rid: (p_model, p_final) for rid, p_model, p_final in client_preds}

    # client_preds is already sorted by p_final desc
    top1_rid = client_preds[0][0]
    top1_runner = runner_map.get(top1_rid)
    top1_finish = top1_runner['finish_position'] if top1_runner else None
    top1_hit = top1_finish == 1 if top1_finish else False

    top3_preds = client_preds[:3]
    top3_info = []
    top3_hit_count = 0
    for rid, p_model, p_final in top3_preds:
        r = runner_map.get(rid)
        if r:
            finish_pos = r.get('finish_position')
            hit = finish_pos is not None and finish_pos <= 3
            if hit:
                top3_hit_count += 1
            top3_info.append({
                'runner_id': rid,
                'horse_no': r.get('horse_no'),
                'finish_pos': finish_pos,
                'predicted_prob': p_final,
                'hit': hit,
            })

    total_bets = 0
    total_returns = 0
    for rid, p_model, p_final in client_preds:
        r = runner_map.get(rid)
        if not r:
            continue
        odds = r.get('win_odds')
        if odds and odds > 1:
            ev = p_final * odds - 1
            if ev > 0.15 and r.get('finish_position'):
                bet_amount = 100
                total_bets += bet_amount
                if r['finish_position'] == 1:
                    total_returns += bet_amount * odds

    roi_percent = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0

    winner = finished[0]
    winner_odds = winner.get('win_odds')
    winner_pred_tuple = pred_map.get(winner['runner_id'])
    winner_p_model = winner_pred_tuple[0] if winner_pred_tuple else None

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
        'top1_pick_runner_id': top1_rid,
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
    parser.add_argument('--race-ids', help='Comma-separated race IDs to review')
    args = parser.parse_args()

    today = datetime.now(HKT)
    date_str = args.date or today.strftime('%Y-%m-%d')

    supabase = get_supabase()

    if args.race_ids:
        race_ids = [x.strip() for x in args.race_ids.split(',') if x.strip()]
        print(f"[AI Review] Reviewing {len(race_ids)} specific races...")
    elif args.all:
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
