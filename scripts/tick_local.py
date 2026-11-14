#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tick_local.py
One race-day tick on this machine: asks tick_gate.decide() what the database needs,
then runs those phases in-process.

Why local: this account's GitHub Actions scheduler delivers roughly two runs a day
for a */30 cron and lands them 3-8 h late, so odds and same-night results keep
missing their windows. Windows Task Scheduler fires every 15 minutes; the Actions
tick stays as the backup for when this machine is off.

Usage:
  python scripts/tick_local.py             # decide and do the work
  python scripts/tick_local.py --dry-run   # decide and log, no writes
"""
import os
import sys
import argparse

if sys.stdout is None:  # running under pythonw.exe from Task Scheduler
    sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    sys.stderr = open(os.devnull, 'w', encoding='utf-8')

sys.path.insert(0, os.path.dirname(__file__))

import auto_pilot  # wraps stdout as utf-8; must happen before the tee below
from datetime import datetime

LOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs', 'tick_local.log'))
MAX_LOG_BYTES = 512 * 1024


class Tee:
    def __init__(self, stream, fh):
        self.stream = stream
        self.fh = fh

    def write(self, data):
        for target in (self.stream, self.fh):
            try:
                target.write(data)
            except Exception:
                pass
        return len(data)

    def flush(self):
        for target in (self.stream, self.fh):
            try:
                target.flush()
            except Exception:
                pass


def open_log():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_BYTES:
        os.replace(LOG_PATH, LOG_PATH + '.1')
    return open(LOG_PATH, 'a', encoding='utf-8', buffering=1)


def run_phase(name: str, fn) -> bool:
    print(f"\n--- {name}")
    try:
        fn()
        return True
    except Exception as e:
        print(f"[ERROR] {name}: {e}")
        return False


def tick(dry_run: bool = False) -> int:
    import tick_gate
    from common import get_supabase

    if not tick_gate.URL or not tick_gate.KEY:
        print('[TICK] no Supabase credentials — nothing to do')
        return 1

    now = datetime.now(tick_gate.HKT)
    today = now.strftime('%Y-%m-%d')
    d = tick_gate.decide(now, today)
    print(f"[TICK] {now.strftime('%Y-%m-%d %H:%M')} HKT — odds={d['odds']} "
          f"archive={d['archive']} discover={d['discover']} ({d['reason']})")

    if not (d['odds'] or d['archive'] or d['discover']):
        return 0

    supabase = get_supabase()
    failures = 0

    if d['discover']:
        tick_gate.mark_discovery_attempt(today)

        def _discover():
            upcoming = auto_pilot.discover_upcoming_race_days(lookahead_days=7)
            scraped = auto_pilot.scrape_new_race_days(supabase, upcoming, dry_run=dry_run)
            print(f"  [Discover] {len(upcoming)} race days checked, {scraped} scraped")

        failures += not run_phase('Phase 1: discover race days', _discover)

    if d['odds']:
        failures += not run_phase(
            'Phase 1.5: inject live odds',
            lambda: auto_pilot.inject_odds_for_upcoming_races(supabase, dry_run=dry_run))

    if d['archive']:
        def _archive():
            unfinished = auto_pilot.find_unfinished_past_races(supabase)
            archived, reviewed = auto_pilot.archive_past_races(supabase, unfinished, dry_run=dry_run)
            print(f"  [Archive] {archived} races archived, {reviewed} AI reviews")

        failures += not run_phase('Phase 2: archive results + AI review', _archive)

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Local race-day tick')
    parser.add_argument('--dry-run', action='store_true', help='Decide and log, no writes')
    args = parser.parse_args()

    sys.stdout = Tee(sys.stdout, open_log())
    start = datetime.now()
    try:
        return tick(dry_run=args.dry_run)
    finally:
        print(f"[TICK] elapsed {(datetime.now() - start).total_seconds():.1f}s\n")
        sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main())
