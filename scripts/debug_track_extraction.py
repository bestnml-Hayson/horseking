#!/usr/bin/env python3
"""Test track_course extraction on a date with races."""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))
from backfill_history import scrape_hkjc_race

out_path = os.path.join(os.path.dirname(__file__), "debug_track_extraction.txt")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    
    # Test with 2026-09-27 ST (Sunday - has races)
    test_cases = [
        ("2026-09-27", "ST", 1),
        ("2026-09-27", "ST", 2),
        ("2026-09-23", "ST", 1),  # Another race day
    ]
    
    with open(out_path, 'w', encoding='utf-8') as f:
        for date_str, venue, race_no in test_cases:
            f.write(f"\n{'='*60}\n")
            f.write(f"Testing: {date_str} {venue} R{race_no}\n")
            f.write(f"{'='*60}\n")
            
            result = scrape_hkjc_race(page, date_str, venue, race_no)
            
            if result:
                f.write(f"✓ Race data extracted successfully\n")
                f.write(f"  distance: {result.get('distance')}\n")
                f.write(f"  going: {result.get('going')}\n")
                f.write(f"  class_level: {result.get('class_level')}\n")
                f.write(f"  track_course: {result.get('track_course')}\n")
                f.write(f"  horses: {len(result.get('horses', []))} entries\n")
            else:
                f.write(f"✗ No data extracted (returned None)\n")
    
    browser.close()
    
    print(f"Debug output written to {out_path}")
