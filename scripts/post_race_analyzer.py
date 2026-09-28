#!/usr/bin/env python3
"""
scripts/post_race_analyzer.py
Post-race analysis: compare AI predictions vs actual results,
compute performance metrics, and identify key factors.

Usage:
  python scripts/post_race_analyzer.py --date 2026-09-27 --venue ST
  python scripts/post_race_analyzer.py --all  # analyze all completed races
"""
import os
import sys
import argparse
import json
from typing import Dict, List, Optional
from datetime import datetime

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed")
    sys.exit(1)


def get_supabase() -> Client:
    url = os.environ.get('SUPABASE_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
    key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')
    if not url or not key:
        print("[FAIL] Missing Supabase env vars")
        sys.exit(1)
    return create_client(url, key)


def analyze_race(supabase: Client, race_id: str) -> Optional[Dict]:
    """Analyze a single race: compare predictions vs results."""
    
    # Get race metadata
    race_info = supabase.table('races').select('race_date, venue, race_no').eq('race_id', race_id).single().execute()
    race_meta = race_info.data or {}
    
    # Get runners with finish positions
    runners_resp = supabase.table('race_runners').select('*').eq('race_id', race_id).execute()
    runners = runners_resp.data or []
    
    if not runners:
        print(f"  [SKIP] {race_id}: no runners")
        return None
    
    # Check if race has results (finish_position populated)
    finished = [r for r in runners if r.get('finish_position') is not None]
    if not finished:
        print(f"  [SKIP] {race_id}: no finish positions (race not completed)")
        return None
    
    # Sort by finish position
    finished.sort(key=lambda r: r['finish_position'])
    
    # Get predictions
    preds_resp = supabase.table('model_predictions').select('*').eq('race_id', race_id).execute()
    preds = preds_resp.data or []
    
    if not preds:
        print(f"  [WARN] {race_id}: no predictions")
        return None
    
    # Build runner_id -> prediction map
    pred_map = {p['runner_id']: p for p in preds}
    
    # Build runner_id -> runner map
    runner_map = {r['runner_id']: r for r in runners}
    
    # Sort predictions by final_prob descending
    sorted_preds = sorted(preds, key=lambda p: p.get('final_prob', 0) or 0, reverse=True)
    
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
                'predicted_prob': p.get('final_prob'),
                'hit': hit
            })
    
    # ROI calculation: simulate $100 bets on positive EV horses
    total_bets = 0
    total_returns = 0
    for p in sorted_preds:
        ev = p.get('expected_value') or 0
        if ev > 0.15:  # Value bet threshold
            r = runner_map.get(p['runner_id'])
            if r and r.get('win_odds') and r.get('finish_position'):
                bet_amount = 100
                total_bets += bet_amount
                if r['finish_position'] == 1:
                    total_returns += bet_amount * r['win_odds']
    
    roi_percent = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0
    
    # Race results
    top4 = finished[:4]
    race_result = {
        'race_id': race_id,
        'first_horse_id': top4[0]['horse_id'] if len(top4) > 0 else None,
        'second_horse_id': top4[1]['horse_id'] if len(top4) > 1 else None,
        'third_horse_id': top4[2]['horse_id'] if len(top4) > 2 else None,
        'fourth_horse_id': top4[3]['horse_id'] if len(top4) > 3 else None,
        'winning_odds': top4[0].get('win_odds') if len(top4) > 0 else None,
    }
    
    # Factor analysis
    key_factors = analyze_factors(runners, sorted_preds, runner_map, pred_map)
    
    # AI performance record
    ai_perf = {
        'race_id': race_id,
        'race_date': race_meta.get('race_date'),
        'venue': race_meta.get('venue'),
        'race_no': race_meta.get('race_no'),
        'top1_pick_runner_id': top1_pred['runner_id'],
        'top1_pick_finish_pos': top1_finish,
        'top1_hit': top1_hit,
        'top3_picks': json.dumps(top3_info),
        'top3_hit_count': top3_hit_count,
        'total_bets': total_bets,
        'total_returns': total_returns,
        'roi_percent': roi_percent,
        'key_factors': json.dumps(key_factors, ensure_ascii=False),
    }
    
    # Optional columns (may not exist in all schemas)
    if key_factors.get('pace'):
        ai_perf['pace_analysis'] = key_factors['pace']
    if key_factors.get('draw'):
        ai_perf['draw_bias'] = key_factors['draw']
    if key_factors.get('market'):
        ai_perf['market_move'] = key_factors['market']
    
    return {
        'race_result': race_result,
        'ai_performance': ai_perf,
        'race_meta': race_meta,
        'runners': runners,
        'summary': {
            'race_id': race_id,
            'top1_hit': top1_hit,
            'top3_hit_count': top3_hit_count,
            'roi_percent': roi_percent,
            'winner_odds': race_result['winning_odds'],
        }
    }


def analyze_factors(runners: List[Dict], sorted_preds: List[Dict], 
                    runner_map: Dict, pred_map: Dict) -> Dict:
    """Analyze key factors that influenced the race outcome."""
    factors = {
        'pace': '',
        'draw': '',
        'market': '',
        'factors': []
    }
    
    finished = [r for r in runners if r.get('finish_position') is not None]
    if not finished:
        return factors
    
    finished.sort(key=lambda r: r['finish_position'])
    winner = finished[0]
    
    # 1. Draw bias analysis
    winner_draw = winner.get('draw') or 0
    avg_draw = sum(r.get('draw', 7) for r in finished) / len(finished)
    
    if winner_draw <= 3:
        factors['draw'] = f'內檔優勢明顯，冠軍馬 {winner_draw} 檔節省腳程'
        factors['factors'].append({
            'type': 'draw_bias',
            'description': f'內檔 (1-3檔) 沿途節省腳程，突顯優勢',
            'impact': 'positive'
        })
    elif winner_draw >= 10:
        factors['draw'] = f'外檔 {winner_draw} 檔仍能奪冠，顯示馬匹實力'
        factors['factors'].append({
            'type': 'draw_bias',
            'description': f'外檔 ({winner_draw}檔) 克服不利條件奪冠',
            'impact': 'remarkable'
        })
    
    # 2. Market move analysis (odds vs prediction)
    winner_odds = winner.get('win_odds') or 0
    winner_pred = pred_map.get(winner['runner_id'])
    winner_prob = winner_pred.get('final_prob', 0) if winner_pred else 0
    
    if winner_odds > 10 and winner_prob < 0.10:
        factors['market'] = f'冷門馬 {winner_odds}x 爆冷，AI 預測概率僅 {winner_prob*100:.1f}%'
        factors['factors'].append({
            'type': 'upset',
            'description': f'大冷門：賠率 {winner_odds}x，AI 預測勝率 {winner_prob*100:.1f}%',
            'impact': 'upset'
        })
    elif winner_odds < 5 and winner_prob > 0.20:
        factors['market'] = f'熱門馬 {winner_odds}x 順利奪冠，AI 預測準確'
        factors['factors'].append({
            'type': 'favorite_wins',
            'description': f'熱門馬 {winner_odds}x 奪冠，AI 預測勝率 {winner_prob*100:.1f}%',
            'impact': 'expected'
        })
    
    # 3. Pace analysis (based on weight and draw)
    avg_weight = sum(r.get('actual_weight', 126) for r in finished) / len(finished)
    if avg_weight < 122:
        factors['pace'] = '快步速，前速馬有利'
        factors['factors'].append({
            'type': 'pace',
            'description': f'平均負磅 {avg_weight:.1f} 磅，快步速有利前領馬',
            'impact': 'pace_fast'
        })
    elif avg_weight > 128:
        factors['pace'] = '慢步速，後追馬有利'
        factors['factors'].append({
            'type': 'pace',
            'description': f'平均負磅 {avg_weight:.1f} 磅，慢步速有利後追馬',
            'impact': 'pace_slow'
        })
    
    # 4. AI prediction accuracy
    top3_preds = sorted_preds[:3]
    ai_hits = sum(1 for p in top3_preds if runner_map.get(p['runner_id'], {}).get('finish_position', 99) <= 3)
    
    if ai_hits >= 2:
        factors['factors'].append({
            'type': 'ai_accuracy',
            'description': f'AI 前三膽命中 {ai_hits}/3，預測準確',
            'impact': 'ai_good'
        })
    elif ai_hits == 0:
        factors['factors'].append({
            'type': 'ai_miss',
            'description': f'AI 前三膽全數落空，可能因素未考慮',
            'impact': 'ai_bad'
        })
    
    return factors


def write_results(supabase: Client, analysis: Dict, runners: List[Dict]):
    """Write analysis results to Supabase."""
    race_result = analysis['race_result']
    ai_perf = analysis['ai_performance']
    race_meta = analysis['race_meta']
    
    # Get race metadata for race_results
    race_id = race_result['race_id']
    
    # Insert race_results (per-runner schema)
    finished_runners = [r for r in runners if r.get('finish_position') is not None]
    for r in finished_runners:
        horse_name = r.get('horse_name') or r.get('horse_id') or f"Horse_{r.get('horse_no', 'unknown')}"
        result_row = {
            'race_id': race_id,
            'race_date': race_meta.get('race_date'),
            'venue': race_meta.get('venue'),
            'race_no': race_meta.get('race_no'),
            'finish_position': r['finish_position'],
            'horse_no': r.get('horse_no'),
            'horse_name': horse_name,
            'jockey': r.get('jockey'),
            'trainer': r.get('trainer'),
            'win_odds': r.get('win_odds'),
            'plc_odds': r.get('plc_odds'),
        }
        # Upsert on unique constraint (race_id, horse_no)
        try:
            supabase.table('race_results').upsert(result_row, on_conflict='race_id,horse_no').execute()
        except Exception as e:
            print(f"    [WARN] Failed to insert {horse_name}: {e}")
    
    # Upsert ai_performance (per-race summary)
    try:
        supabase.table('ai_performance').upsert(ai_perf, on_conflict='race_id').execute()
    except Exception as e:
        # If optional columns don't exist, retry without them
        if 'column' in str(e).lower():
            ai_perf_core = {k: v for k, v in ai_perf.items() 
                           if k not in ['pace_analysis', 'draw_bias', 'market_move']}
            supabase.table('ai_performance').upsert(ai_perf_core, on_conflict='race_id').execute()
        else:
            raise
    
    print(f"  [OK] Written {len(finished_runners)} runners to race_results + ai_performance")


def main():
    parser = argparse.ArgumentParser(description='Post-race AI performance analyzer')
    parser.add_argument('--date', type=str, help='Race date (YYYY-MM-DD)')
    parser.add_argument('--venue', type=str, choices=['ST', 'HV'], help='Venue')
    parser.add_argument('--all', action='store_true', help='Analyze all completed races')
    args = parser.parse_args()
    
    supabase = get_supabase()
    
    if args.all:
        # Get all races with finish positions
        print("[Analyzer] Analyzing all completed races...")
        runners_resp = supabase.table('race_runners').select('race_id, finish_position').not_.is_('finish_position', 'null').execute()
        race_ids = list(set(r['race_id'] for r in (runners_resp.data or [])))
        race_ids.sort()
    elif args.date and args.venue:
        # Get races for specific date/venue
        date_path = args.date.replace('-', '')
        races_resp = supabase.table('races').select('race_id').eq('race_date', args.date).eq('venue', args.venue).execute()
        race_ids = [r['race_id'] for r in (races_resp.data or [])]
    else:
        print("[FAIL] Specify --date + --venue or --all")
        sys.exit(1)
    
    print(f"[Analyzer] Found {len(race_ids)} races to analyze")
    
    results = []
    for race_id in race_ids:
        print(f"\n  Analyzing {race_id}...")
        analysis = analyze_race(supabase, race_id)
        if analysis:
            write_results(supabase, analysis, analysis['runners'])
            results.append(analysis['summary'])
    
    # Print summary
    if results:
        print("\n" + "="*60)
        print("ANALYSIS SUMMARY")
        print("="*60)
        total_races = len(results)
        top1_hits = sum(1 for r in results if r['top1_hit'])
        top3_total = sum(r['top3_hit_count'] for r in results)
        avg_roi = sum(r['roi_percent'] for r in results) / total_races if total_races > 0 else 0
        
        print(f"Total races analyzed: {total_races}")
        print(f"Top 1 hit rate: {top1_hits}/{total_races} ({top1_hits/total_races*100:.1f}%)")
        print(f"Top 3 avg hits: {top3_total/total_races:.1f} per race")
        print(f"Avg ROI: {avg_roi:+.1f}%")
        print("="*60)


if __name__ == '__main__':
    main()
