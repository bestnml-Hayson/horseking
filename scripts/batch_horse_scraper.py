#!/usr/bin/env python3
"""Batch scrape horse profiles for a specific race date."""
import argparse
import os
import sys
import json
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from horse_scraper import scrape_horse_profile, update_horse_data

# Load env
env_path = Path(__file__).parent.parent / '.env.local'
with open(env_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from supabase import create_client

def get_horses_from_date(race_date: str) -> List[str]:
    """Get all unique horse codes from races on a specific date."""
    url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    supabase = create_client(url, key)
    
    # Get all races on this date
    races = supabase.table('races').select('race_id').eq('race_date', race_date).execute()
    
    if not races.data:
        print(f"No races found for {race_date}")
        return []
    
    race_ids = [r['race_id'] for r in races.data]
    print(f"Found {len(race_ids)} races on {race_date}")
    
    # Get all unique horse_ids from race_runners
    all_horses = set()
    for race_id in race_ids:
        runners = supabase.table('race_runners').select('horse_id').eq('race_id', race_id).execute()
        for runner in runners.data:
            if runner.get('horse_id'):
                all_horses.add(runner['horse_id'])
    
    print(f"Found {len(all_horses)} unique horses")
    return list(all_horses)

def get_latest_race_date(supabase) -> str:
    """Get the most recent race date from the database."""
    result = supabase.table('races').select('race_date').order('race_date', desc=True).limit(1).execute()
    if result.data:
        return result.data[0]['race_date']
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')


def batch_scrape_horses(race_date: str, limit: int = 0):
    """Scrape all horses from a specific race date."""
    horse_codes = get_horses_from_date(race_date)

    if not horse_codes:
        return

    if limit > 0:
        horse_codes = horse_codes[:limit]

    print(f"\nScraping {len(horse_codes)} horse profiles...")
    
    success_count = 0
    fail_count = 0
    
    for i, horse_code in enumerate(horse_codes, 1):
        print(f"\n[{i}/{len(horse_codes)}] Scraping {horse_code}...")
        
        try:
            profile = scrape_horse_profile(horse_code)
            
            if profile and profile.get('career_starts') is not None:
                print(f"  [OK] Age: {profile.get('age')}, Starts: {profile.get('career_starts')}, Wins: {profile.get('career_wins')}, Prize: ${profile.get('total_prize_money', 0):,}")
                print(f"  [OK] Form history: {len(profile.get('form_history', []))} records")
                
                # Update database
                update_horse_data(horse_code, profile)
                success_count += 1
            else:
                print(f"  [FAIL] Failed to extract profile data")
                fail_count += 1
                
        except Exception as e:
            print(f"  [FAIL] Error: {e}")
            fail_count += 1
    
    print(f"\n{'='*60}")
    print(f"Batch scrape completed:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Total: {len(horse_codes)}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Batch scrape horse profiles')
    parser.add_argument('--date', type=str, default=None, help='Race date to scrape horses from (YYYY-MM-DD, default: latest race date in DB)')
    parser.add_argument('--limit', type=int, default=0, help='Max number of horses to scrape (0 = all)')
    args = parser.parse_args()

    if args.date:
        target_date = args.date
    else:
        env_path = Path(__file__).parent.parent / '.env.local'
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key] = value
        from supabase import create_client
        url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
        key = os.getenv('SUPABASE_SERVICE_KEY')
        supa = create_client(url, key)
        target_date = get_latest_race_date(supa)

    print(f"Batch scraping horse profiles for {target_date}")
    print(f"{'='*60}")

    batch_scrape_horses(target_date, args.limit)
