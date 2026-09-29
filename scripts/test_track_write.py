#!/usr/bin/env python3
"""Manual test: scrape one race and write to database with track_course."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from backfill_history import scrape_hkjc_race
from playwright.sync_api import sync_playwright

# Load env
env_path = Path(__file__).parent.parent / '.env.local'
with open(env_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from supabase import create_client
url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

# Scrape one race
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    
    result = scrape_hkjc_race(page, '2026-09-27', 'ST', 1)
    browser.close()

if not result:
    print("ERROR: Failed to scrape race")
    sys.exit(1)

print(f"Scraped race data:")
print(f"  distance: {result.get('distance')}")
print(f"  going: {result.get('going')}")
print(f"  class_level: {result.get('class_level')}")
print(f"  track_course: {result.get('track_course')}")
print(f"  horses: {len(result.get('horses', []))}")

# Manually write to database
race_id = result['race_id']
print(f"\nWriting to database: {race_id}")

# Delete existing
try:
    supabase.table('races').delete().eq('race_id', race_id).execute()
    print("  Deleted existing race record")
except Exception as e:
    print(f"  Delete error: {e}")

# Insert new
race_row = {
    'race_id': race_id,
    'race_date': result['race_date'],
    'venue': result['venue'],
    'race_no': result['race_no'],
    'distance': result.get('distance'),
    'going': result.get('going'),
    'class_level': result.get('class_level'),
    'track_course': result.get('track_course'),
}

try:
    supabase.table('races').insert(race_row).execute()
    print("  Inserted new race record")
except Exception as e:
    print(f"  Insert error: {e}")

# Verify
verify = supabase.table('races').select('race_id, track_course, going, distance').eq('race_id', race_id).execute()
if verify.data:
    print(f"\nVerification:")
    print(f"  race_id: {verify.data[0]['race_id']}")
    print(f"  track_course: {verify.data[0]['track_course']}")
    print(f"  going: {verify.data[0]['going']}")
    print(f"  distance: {verify.data[0]['distance']}")
else:
    print("\nERROR: Race not found in database after insert")
