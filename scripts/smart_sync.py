#!/usr/bin/env python3
"""
scripts/smart_sync.py
Smart scheduler: determines sync mode based on date/time and executes accordingly.

Modes:
  skip         — No action (non-race day, wrong time)
  positioning  — Scrape race cards only (day before race, or race day early)
  odds         — Full sync: scrape odds + Benter model (race day, >15 min before next race)
  highfreq     — High-frequency odds polling (race day, within 15 min of next race)

HKJC Race Days:
  ST (沙田): Wednesday, Saturday
  HV (跑馬地): Tuesday, Thursday, Sunday

Typical Race Times:
  ST day session:   first race ~13:00, intervals ~25-30 min
  HV night session: first race ~19:00, intervals ~25-30 min
"""
import os
import sys
import subprocess
from datetime import datetime, timedelta, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

RACE_DAY_WEEKDAYS = {
    'ST': [2, 5],       # Wed, Sat
    'HV': [1, 3, 6],    # Tue, Thu, Sun
}

RACE_INTERVALS = [0, 25, 25, 30, 25, 30, 25, 30, 25, 30, 25, 30]

FIRST_RACE_TIME = {'ST': dtime(13, 0), 'HV': dtime(19, 0)}


def get_venue_for_date(dt: datetime) -> Optional[str]:
    wd = dt.weekday()
    for venue, days in RACE_DAY_WEEKDAYS.items():
        if wd in days:
            return venue
    return None


def estimate_race_times(date_str: str, venue: str, num_races: int = 11):
    d = datetime.strptime(date_str, '%Y-%m-%d').date()
    first = FIRST_RACE_TIME.get(venue, dtime(13, 0))
    races = []
    for i in range(num_races):
        offset = sum(RACE_INTERVALS[:i]) if i < len(RACE_INTERVALS) else i * 28
        start = datetime.combine(d, first) + timedelta(minutes=offset)
        races.append({'race_no': i + 1, 'start_time': start})
    return races


def determine_mode(now: datetime, venue: Optional[str], race_times: list) -> str:
    if venue is None:
        tomorrow = now.date() + timedelta(days=1)
        tomorrow_dt = datetime.combine(tomorrow, dtime(12, 0))
        if get_venue_for_date(tomorrow_dt):
            if now.hour in (12, 20):
                return 'positioning'
        return 'skip'

    next_race = None
    for race in race_times:
        if race['start_time'] > now:
            next_race = race
            break

    if next_race is None:
        return 'skip'

    minutes_to_race = (next_race['start_time'] - now).total_seconds() / 60

    if minutes_to_race <= 15:
        return 'highfreq'
    elif minutes_to_race <= 180:
        return 'odds'
    else:
        return 'positioning'


def run_cmd(cmd: str) -> int:
    print(f"\n>>> {cmd}")
    return subprocess.run(cmd, shell=True).returncode


def main():
    now_hkt = datetime.now(HKT)
    now = now_hkt.replace(tzinfo=None)
    date_str = now.strftime('%Y-%m-%d')
    venue = get_venue_for_date(now)
    race_times = estimate_race_times(date_str, venue or 'ST')

    mode = determine_mode(now, venue, race_times)

    print("=" * 60)
    print(f"[SmartSync] {now.strftime('%Y-%m-%d %H:%M:%S HKT')}")
    print(f"  Venue:  {venue or 'N/A (non-race day)'}")
    print(f"  Mode:   {mode}")
    if race_times:
        next_upcoming = [r for r in race_times if r['start_time'] > now]
        if next_upcoming:
            nr = next_upcoming[0]
            print(f"  Next:   R{nr['race_no']} @ {nr['start_time'].strftime('%H:%M')}")
    print("=" * 60)

    if mode == 'skip':
        print("[SmartSync] No action needed.")
        sys.exit(0)

    env = os.environ.copy()
    venue_arg = venue if venue else 'auto'

    if mode == 'positioning':
        print("[SmartSync] Positioning mode: scraping race cards...")
        rc = run_cmd(f"python scripts/auto_scraper.py --date {date_str} --venue {venue_arg}")
        sys.exit(rc)

    elif mode == 'odds':
        print("[SmartSync] Odds mode: full sync + Benter...")
        rc1 = run_cmd(f"python scripts/auto_scraper.py --date {date_str} --venue {venue_arg}")
        rc2 = run_cmd("python scripts/benter_model.py supabase")
        sys.exit(max(rc1, rc2))

    elif mode == 'highfreq':
        print("[SmartSync] High-frequency mode: launching pacing loop...")
        rc = run_cmd(f"python scripts/live_high_frequency_pacing.py --date {date_str} --venue {venue_arg}")
        sys.exit(rc)


if __name__ == '__main__':
    main()
