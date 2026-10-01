#!/usr/bin/env python3
"""
scripts/live_high_frequency_pacing.py
High-frequency odds polling loop — runs every 10s until the next race starts.

Usage:
  python scripts/live_high_frequency_pacing.py --date 2026-10-01 --venue ST

Designed to be launched by smart_sync.py when mode == 'highfreq'.
Opens a persistent Playwright browser, loops:
  1. Scrape live odds for all races
  2. Upsert win_odds into Supabase race_runners
  3. Run Benter model to recalculate predictions
  4. Sleep 10s
  5. Exit when the next estimated race start time has passed
"""
import os
import sys
import time
import argparse
import subprocess
from datetime import datetime, timedelta, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed. Run: pip install supabase")
    sys.exit(1)

from auto_scraper import (
    get_supabase_client,
    scrape_odds_only,
    update_odds_in_supabase,
    estimate_race_times,
    detect_venue_from_hkjc,
    auto_detect_venue,
)

POLL_INTERVAL = 10
MAX_LOOP_MINUTES = 20


def now_hkt():
    return datetime.now(HKT).replace(tzinfo=None)


def get_supabase_or_exit() -> Client:
    supabase = get_supabase_client()
    if not supabase:
        print("[FAIL] Cannot connect to Supabase")
        sys.exit(1)
    return supabase


def find_next_race(race_times: list, now: datetime) -> Optional[dict]:
    for race in race_times:
        if race['start_time'] > now:
            return race
    return None


def run_benter():
    print("  [Benter] Running model...")
    rc = subprocess.run(
        [sys.executable, "scripts/benter_model.py", "supabase"],
        capture_output=False,
    )
    if rc.returncode != 0:
        print(f"  [Benter] Exit code {rc.returncode}")
    return rc.returncode


def main():
    parser = argparse.ArgumentParser(description='High-frequency odds polling loop')
    parser.add_argument('--date', required=True, help='Race date (YYYY-MM-DD)')
    parser.add_argument('--venue', required=True, choices=['ST', 'HV', 'auto'], help='Venue code')
    parser.add_argument('--max-minutes', type=int, default=MAX_LOOP_MINUTES, help='Max loop duration in minutes')
    args = parser.parse_args()

    date_str = args.date
    if args.venue == 'auto':
        venue = detect_venue_from_hkjc(date_str)
        if not venue:
            from datetime import datetime as dt
            venue = auto_detect_venue(dt.now(HKT).replace(tzinfo=None))
        if not venue:
            print("[FAIL] Could not detect venue")
            sys.exit(1)
    else:
        venue = args.venue
    max_seconds = args.max_minutes * 60

    supabase = get_supabase_or_exit()
    race_times = estimate_race_times(date_str, venue)
    start_wall = time.time()

    print("=" * 60)
    print(f"[HighFreq] {date_str} {venue}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print(f"  Max duration:  {args.max_minutes} min")
    next_race = find_next_race(race_times, now_hkt())
    if next_race:
        mins = (next_race['start_time'] - now_hkt()).total_seconds() / 60
        print(f"  Next race:     R{next_race['race_no']} @ {next_race['start_time'].strftime('%H:%M')} ({mins:.0f} min)")
    print("=" * 60)

    loop_count = 0

    while True:
        elapsed = time.time() - start_wall
        if elapsed > max_seconds:
            print(f"\n[HighFreq] Max duration ({args.max_minutes} min) reached. Exiting.")
            break

        now = now_hkt()
        next_race = find_next_race(race_times, now)

        if next_race is None:
            print("\n[HighFreq] All races have started or passed. Exiting.")
            break

        mins_to_race = (next_race['start_time'] - now).total_seconds() / 60

        if mins_to_race < -5:
            print(f"\n[HighFreq] R{next_race['race_no']} started {abs(mins_to_race):.0f} min ago. Moving on.")
            break

        loop_count += 1
        ts = now.strftime('%H:%M:%S')
        print(f"\n--- Loop #{loop_count} @ {ts} (R{next_race['race_no']} in {mins_to_race:.1f} min) ---")

        try:
            odds_map = scrape_odds_only(date_str, venue)
            if odds_map:
                update_odds_in_supabase(supabase, date_str, venue, odds_map)
                run_benter()
            else:
                print("  [WARN] No odds scraped this loop")
        except Exception as e:
            print(f"  [ERROR] {e}")

        if mins_to_race <= 0:
            print(f"\n[HighFreq] Race R{next_race['race_no']} has started. Final sync done. Exiting.")
            break

        remaining = (next_race['start_time'] - now_hkt()).total_seconds()
        sleep_time = min(POLL_INTERVAL, max(remaining, 0)) if remaining > 0 else POLL_INTERVAL
        time.sleep(sleep_time)

    print(f"\n[HighFreq] Completed {loop_count} loops in {(time.time() - start_wall) / 60:.1f} min")


if __name__ == '__main__':
    main()
