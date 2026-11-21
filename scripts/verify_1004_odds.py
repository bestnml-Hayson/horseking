#!/usr/bin/env python3
"""
Verify and fix 10/4 odds in database.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_supabase


def check_odds():
    supabase = get_supabase()
    if not supabase:
        print("[FAIL] Cannot connect to Supabase")
        return

    # Check R11 odds
    resp = supabase.table('race_runners').select('runner_id,horse_no,win_odds').eq('race_id', 'ST-20261004-11').order('horse_no').execute()
    runners = resp.data or []

    print(f"R11: {len(runners)} runners")
    odds_10_count = sum(1 for r in runners if r.get('win_odds') == 10.0)
    odds_valid_count = sum(1 for r in runners if r.get('win_odds') and r.get('win_odds') > 1.01 and r.get('win_odds') != 10.0)

    print(f"  Odds = 10.0: {odds_10_count}")
    print(f"  Valid odds: {odds_valid_count}")

    if odds_10_count > 0:
        print("\n[WARN] Still has 10.0 default odds. Need to re-scrape.")
    else:
        print("\n[OK] All odds are real values.")

    # Show sample
    for r in runners[:5]:
        print(f"  #{r['horse_no']}: {r['win_odds']}")


if __name__ == '__main__':
    check_odds()
