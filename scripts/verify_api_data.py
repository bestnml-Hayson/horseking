#!/usr/bin/env python3
"""Verify what Supabase REST API returns vs what production API shows."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from common import get_supabase

sb = get_supabase()

print("=== Direct DB queries (service_role key) ===")

# R7 race_runners
r = sb.table('race_runners').select('horse_no,win_odds,finish_position').eq('race_id','ST-20261004-07').order('horse_no').execute()
print("\nR7 race_runners (first 5):")
for h in (r.data or [])[:5]:
    print(f"  #{h['horse_no']}: odds={h['win_odds']}, finish={h['finish_position']}")

# R7 ai_performance
r2 = sb.table('ai_performance').select('race_id,total_bets,total_returns,roi_percent').eq('race_id','ST-20261004-07').single().execute()
print(f"\nR7 ai_performance: {r2.data}")

# R7 model_predictions - top 3 by final_prob
r3 = sb.table('model_predictions').select('runner_id,raw_model_prob,final_prob,expected_value').eq('race_id','ST-20261004-07').execute()
preds = sorted(r3.data or [], key=lambda x: -(x.get('final_prob') or 0))
print(f"\nR7 model_predictions (top 5 by final_prob):")
for p in preds[:5]:
    print(f"  {p['runner_id']}: final_prob={p['final_prob']}, ev={p['expected_value']}")

# Now simulate what ai_review.py would compute
runner_map = {h['horse_no']: h for h in (r.data or [])}
print(f"\n=== Simulating ROI computation ===")
total_bets = 0
total_returns = 0
for p in preds:
    ev = p.get('expected_value') or 0
    if ev > 0.15:
        runner_id = p['runner_id']
        horse_no = int(runner_id.split('_H')[1])
        runner = runner_map.get(horse_no)
        if runner and runner.get('win_odds') and runner.get('finish_position'):
            bet = 100
            total_bets += bet
            if runner['finish_position'] == 1:
                ret = bet * runner['win_odds']
                total_returns += ret
                print(f"  BET: {runner_id}, odds={runner['win_odds']}, finish={runner['finish_position']}, return={ret}")
            else:
                print(f"  BET: {runner_id}, odds={runner['win_odds']}, finish={runner['finish_position']}, LOST")

roi = ((total_returns - total_bets) / total_bets * 100) if total_bets > 0 else 0
print(f"\nComputed: bets={total_bets}, returns={total_returns}, roi={roi:.1f}%")
print(f"DB stored: bets={r2.data['total_bets']}, returns={r2.data['total_returns']}, roi={r2.data['roi_percent']}")
