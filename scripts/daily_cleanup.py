#!/usr/bin/env python3
"""
scripts/daily_cleanup.py
Daily automated data cleanup:
  1. Remove future race data (accidentally scraped)
  2. Remove orphaned records (runners without races)
  3. Clean up old temporary data
  4. Verify data integrity

Usage:
  python scripts/daily_cleanup.py --days 7
  python scripts/daily_cleanup.py --dry-run
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List

try:
    from supabase import create_client, Client
except ImportError:
    print("[FAIL] supabase-py not installed. Run: pip install supabase")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(__file__))
from common import get_supabase


def cleanup_future_races(supabase: Client, dry_run: bool = False) -> int:
    """Remove race data for future dates."""
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n[1/4] Cleaning future races (date > {today})...")

    # Get all races with future dates
    future_races = supabase.table('races') \
        .select('race_id') \
        .gt('race_date', today) \
        .execute()

    if not future_races.data:
        print("  [OK] No future races found")
        return 0

    race_ids = [r['race_id'] for r in future_races.data]
    print(f"  Found {len(race_ids)} future races")

    if dry_run:
        print(f"  [DRY RUN] Would delete {len(race_ids)} races")
        return len(race_ids)

    # Delete related runners first
    for race_id in race_ids:
        supabase.table('race_runners').delete().eq('race_id', race_id).execute()
        supabase.table('model_predictions').delete().eq('race_id', race_id).execute()

    # Delete races
    supabase.table('races').delete().in_('race_id', race_ids).execute()
    print(f"  [OK] Deleted {len(race_ids)} future races")
    return len(race_ids)


def cleanup_orphaned_runners(supabase: Client, dry_run: bool = False) -> int:
    """Remove runners that don't have a corresponding race."""
    print("\n[2/4] Cleaning orphaned runners...")

    # Get all race IDs
    all_races = supabase.table('races').select('race_id').execute()
    valid_race_ids = set(r['race_id'] for r in all_races.data) if all_races.data else set()

    # Get all runners
    all_runners = supabase.table('race_runners').select('runner_id, race_id').execute()
    orphaned = [r for r in all_runners.data if r['race_id'] not in valid_race_ids] if all_runners.data else []

    print(f"  Found {len(orphaned)} orphaned runners")

    if dry_run or not orphaned:
        return len(orphaned)

    # Delete orphaned runners in batches
    batch_size = 100
    for i in range(0, len(orphaned), batch_size):
        batch = orphaned[i:i + batch_size]
        runner_ids = [r['runner_id'] for r in batch]
        supabase.table('race_runners').delete().in_('runner_id', runner_ids).execute()

    print(f"  [OK] Deleted {len(orphaned)} orphaned runners")
    return len(orphaned)


def cleanup_old_predictions(supabase: Client, days: int = 90, dry_run: bool = False) -> int:
    """Remove predictions older than N days."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    print(f"\n[3/4] Cleaning predictions older than {days} days (before {cutoff_date})...")

    # Get old race IDs
    old_races = supabase.table('races') \
        .select('race_id') \
        .lt('race_date', cutoff_date) \
        .execute()

    if not old_races.data:
        print("  [OK] No old races found")
        return 0

    race_ids = [r['race_id'] for r in old_races.data]
    print(f"  Found {len(race_ids)} old races")

    if dry_run:
        print(f"  [DRY RUN] Would delete predictions for {len(race_ids)} races")
        return len(race_ids)

    # Delete predictions in batches
    batch_size = 100
    total_deleted = 0
    for i in range(0, len(race_ids), batch_size):
        batch = race_ids[i:i + batch_size]
        supabase.table('model_predictions').delete().in_('race_id', batch).execute()
        total_deleted += len(batch)

    print(f"  [OK] Deleted predictions for {total_deleted} old races")
    return total_deleted


def verify_data_integrity(supabase: Client) -> Dict[str, int]:
    """Run basic integrity checks."""
    print("\n[4/4] Verifying data integrity...")

    checks = {}

    # Count races
    races = supabase.table('races').select('race_id', count='exact').execute()
    checks['total_races'] = races.count if races.count else 0

    # Count runners
    runners = supabase.table('race_runners').select('runner_id', count='exact').execute()
    checks['total_runners'] = runners.count if runners.count else 0

    # Count predictions
    predictions = supabase.table('model_predictions').select('prediction_id', count='exact').execute()
    checks['total_predictions'] = predictions.count if predictions.count else 0

    # Check for null odds in today's races
    today = datetime.now().strftime('%Y-%m-%d')
    today_races = supabase.table('races').select('race_id').eq('race_date', today).execute()
    if today_races.data:
        race_ids = [r['race_id'] for r in today_races.data]
        null_odds = supabase.table('race_runners') \
            .select('runner_id') \
            .in_('race_id', race_ids) \
            .is_('win_odds', 'null') \
            .execute()
        checks['null_odds_today'] = len(null_odds.data) if null_odds.data else 0
    else:
        checks['null_odds_today'] = 0

    print(f"  Races: {checks['total_races']}")
    print(f"  Runners: {checks['total_runners']}")
    print(f"  Predictions: {checks['total_predictions']}")
    print(f"  Null odds (today): {checks['null_odds_today']}")

    return checks


def main():
    parser = argparse.ArgumentParser(description='Daily automated data cleanup')
    parser.add_argument('--days', type=int, default=90, help='Days to keep predictions (default: 90)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    args = parser.parse_args()

    try:
        supabase = get_supabase()
        print(f"[DailyCleanup] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print(f"  Prediction retention: {args.days} days")
    except Exception as e:
        print(f"[FAIL] Supabase connection error: {e}")
        sys.exit(1)

    # Run cleanup steps
    future_deleted = cleanup_future_races(supabase, args.dry_run)
    orphaned_deleted = cleanup_orphaned_runners(supabase, args.dry_run)
    old_predictions_deleted = cleanup_old_predictions(supabase, args.days, args.dry_run)

    # Verify integrity
    integrity = verify_data_integrity(supabase)

    # Summary
    print("\n" + "=" * 60)
    print("[DailyCleanup] Summary:")
    print(f"  Future races deleted: {future_deleted}")
    print(f"  Orphaned runners deleted: {orphaned_deleted}")
    print(f"  Old predictions deleted: {old_predictions_deleted}")
    print(f"  Final race count: {integrity['total_races']}")
    print(f"  Final runner count: {integrity['total_runners']}")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] No data was actually deleted")


if __name__ == '__main__':
    main()
