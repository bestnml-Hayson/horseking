#!/usr/bin/env python3
"""
Scrape final win odds from HKJC results page for 2026-10-04 and update race_runners.
"""
import os
import sys
import re
from datetime import datetime
from zoneinfo import ZoneInfo

HKT = ZoneInfo('Asia/Hong_Kong')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_supabase, retry_supabase


def scrape_final_odds(page, date_str: str, venue: str, race_no: int) -> dict:
    """
    Scrape final win odds from HKJC results page.
    Returns: {'horse_no': win_odds, ...}
    """
    date_slash = date_str.replace('-', '/')
    results_url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_slash}&Racecourse={venue}&RaceNo={race_no}"

    try:
        page.goto(results_url, wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(4000)

        # Extract odds from the results table
        odds_data = page.evaluate('''() => {
            const oddsMap = {};
            const tables = document.querySelectorAll('table');

            for (const t of tables) {
                const rows = t.querySelectorAll('tr');
                if (rows.length < 3) continue;

                // Find the results table by looking for "名次" header
                const firstRow = rows[0].querySelectorAll('td, th');
                let hasPositionCol = false;
                let hasOddsCol = false;
                let oddsColIdx = -1;

                for (let i = 0; i < firstRow.length; i++) {
                    const txt = firstRow[i].textContent.trim();
                    if (txt === '名次' || txt === '排名') hasPositionCol = true;
                    if (txt === '獨贏賠率' || txt.includes('獨贏')) {
                        hasOddsCol = true;
                        oddsColIdx = i;
                    }
                }

                if (hasPositionCol && hasOddsCol && oddsColIdx >= 0) {
                    for (let ri = 1; ri < rows.length; ri++) {
                        const cells = rows[ri].querySelectorAll('td');
                        if (cells.length <= oddsColIdx) continue;

                        const posText = cells[0].textContent.trim();
                        const pos = parseInt(posText);
                        if (isNaN(pos) || pos <= 0) continue;

                        // Find horse number
                        let horseNo = 0;
                        for (let ci = 0; ci < cells.length; ci++) {
                            const num = parseInt(cells[ci].textContent.trim());
                            if (!isNaN(num) && num > 0 && num <= 20) {
                                horseNo = num;
                                break;
                            }
                        }

                        const oddsText = cells[oddsColIdx].textContent.trim();
                        const odds = parseFloat(oddsText);
                        if (!isNaN(odds) && odds > 0 && horseNo > 0) {
                            oddsMap[horseNo] = odds;
                        }
                    }
                    break;
                }
            }
            return oddsMap;
        }''')

        return odds_data

    except Exception as e:
        print(f"    [FAIL] R{race_no} odds scrape: {e}")
        return {}


def update_odds_for_date(date_str: str, venue: str):
    """Update win_odds for all races on a given date."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[FAIL] playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    supabase = get_supabase()
    if not supabase:
        sys.exit(1)

    # Fetch races for this date/venue
    query = supabase.table('races').select('race_id,race_no').eq('race_date', date_str).eq('venue', venue)
    resp = query.execute()
    races = resp.data or []

    if not races:
        print(f"[FAIL] No races found for {date_str} {venue}")
        return

    print(f"=" * 60)
    print(f"Update Final Odds - {date_str} {venue}")
    print(f"Races: {len(races)}")
    print(f"=" * 60)

    total_updated = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()

        for race in races:
            race_id = race['race_id']
            race_no = race['race_no']

            print(f"\n  Processing R{race_no} ({race_id})...")

            # Scrape final odds
            odds_map = scrape_final_odds(page, date_str, venue, race_no)

            if not odds_map:
                print(f"    [WARN] No odds scraped")
                continue

            print(f"    [OK] {len(odds_map)} horses with odds")

            # Update race_runners with real odds
            for horse_no, win_odds in odds_map.items():
                resp = supabase.table('race_runners').select('runner_id').eq('race_id', race_id).eq('horse_no', horse_no).execute()
                runners = resp.data or []

                if runners:
                    runner_id = runners[0]['runner_id']
                    retry_supabase(lambda: supabase.table('race_runners').update({
                        'win_odds': win_odds
                    }).eq('runner_id', runner_id).execute())
                    total_updated += 1

        browser.close()

    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"  Total runners updated: {total_updated}")
    print(f"{'=' * 60}")


def main():
    date_str = '2026-10-04'
    venue = 'ST'

    update_odds_for_date(date_str, venue)


if __name__ == '__main__':
    main()
